from django.db import models
from django.db import transaction, IntegrityError
from django.db.models import Max
from django.db.models import Q

from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic

from django.utils.timezone import get_default_timezone
from django.core.exceptions import ObjectDoesNotExist

from DurationField import DurationField
from get_abbrev import get_abbrev

import math
import datetime
import base64
from django.utils.translation import ugettext_lazy as _
import utils
import random
import iso3166
from TagFormat import getValidTagFormatStr, getTagFormatStr

def fixNullUpper( s ):
	if not s:
		return None
	s = (s or u'').strip()
	if s:
		return s.upper()
	else:
		return None

def getSrcStr( fname ):
	fileExtension = os.path.splitext(fname)[1]
	ftype = {
		'.png':		'png',
		'.gif':		'gif',
		'.jpeg':	'jpg',
		'.jpg':		'jpg',
	}[fileExtension.lower()]
	with open(fname, 'rb') as f:
		src = 'data:image/{};base64,{}'.format(ftype, base64.encodestring(f.read()))
	return src

KmToMiles = 0.621371192
MilesToKm = 1.0 / KmToMiles

#----------------------------------------------------------------------------------------
def getCopyName( ModelClass, cur_name ):
	base_name = cur_name
	suffix = u' - Copy('
	if suffix in base_name:
		base_name = base_name[:base_name.index(suffix)]
	for i in xrange(1, 100000):
		new_name = u'{}{}{})'.format( base_name, suffix, i )
		if not Competition.objects.filter(name = new_name).exists():
			return new_name
	return None

#----------------------------------------------------------------------------------------
class SystemInfo(models.Model):
	tag_template = models.CharField( max_length = 24, verbose_name = _('Tag Template'), help_text=_("Template for generating EPC RFID tags.") )

	RFID_SERVER_HOST_DEFAULT = 'localhost'
	RFID_SERVER_PORT_DEFAULT = 50111
	
	rfid_server_host = models.CharField( max_length = 32, default = RFID_SERVER_HOST_DEFAULT, verbose_name = _('RFID Reader Server Host')  )
	rfid_server_port = models.PositiveSmallIntegerField( default = RFID_SERVER_PORT_DEFAULT, verbose_name = _('RFID Reader Server Port') )
	
	reg_closure_minutes = models.IntegerField( default = -1, verbose_name = _('Reg Closure Minutes'), help_text=_('Minutes before race start to close registration for "reg" users.  Use -1 for None.') )
	
	@classmethod
	def get_tag_template_default( cls ):
		tNow = datetime.datetime.now()
		rs = ''.join( '0123456789ABCDEF'[random.randint(1,15)] for i in xrange(4))
		tt = '{}######{:02}'.format( rs, tNow.year % 100 )
		return tt
	
	@classmethod
	def get_singleton( cls ):
		if not cls.objects.exists():
			system_info = cls( tag_template = cls.get_tag_template_default() )
			system_info.save()
			return system_info
		else:
			for system_info in cls.objects.all():
				return system_info
	
	@classmethod
	def get_reg_closure_minutes( cls ):
		return cls.get_singleton().reg_closure_minutes
	
	def save( self, *args, **kwargs ):
		self.tag_template = getValidTagFormatStr( self.tag_template )
		self.rfid_server_host = (self.rfid_server_host or self.RFID_SERVER_HOST_DEFAULT)
		self.rfid_server_port = (self.rfid_server_port or self.RFID_SERVER_PORT_DEFAULT)
		
		return super(SystemInfo, self).save( *args, **kwargs )
		
	class Meta:
		verbose_name = _('SystemInfo')

#----------------------------------------------------------------------------------------

class CategoryFormat(models.Model):
	name = models.CharField( max_length = 32, default = '', verbose_name = _('Name') )
	description = models.CharField( max_length = 80, blank = True, default = '', verbose_name = _('Description') )
	
	@transaction.atomic
	def make_copy( self ):
		categories = self.category_set.all()
		
		category_format_new = self
		category_format_new.pk = None
		category_format_new.save()
		
		for c in categories:
			c.make_copy( category_format_new )
		return category_format_new
	
	@property
	def next_category_seq( self ):
		try:
			return self.category_set.all().aggregate( Max('sequence') )['sequence__max'] + 1
		except:
			return 1
		
	def full_name( self ):
		return ','.join( [self.name, self.description] )
		
	def get_search_text( self ):
		return utils.get_search_text( [self.name, self.description] )
		
	def __unicode__( self ):
		return self.name
		
	class Meta:
		ordering = ['name']
		verbose_name = _('CategoryFormat')
		verbose_name_plural = _('CategoryFormats')

def init_sequence( Class, obj ):
	if not obj.sequence:
		obj.sequence = Class.objects.count() + 1
		
class Category(models.Model):
	format = models.ForeignKey( CategoryFormat, db_index = True )
	code = models.CharField( max_length=16, default='', verbose_name = _('Code') )
	GENDER_CHOICES = (
		(0, _('Men')),
		(1, _('Women')),
		(2, _('Open')),
	)
	gender = models.PositiveSmallIntegerField(choices=GENDER_CHOICES, default = 0, verbose_name = _('Gender') )
	description = models.CharField( max_length = 80, default = '', blank = True, verbose_name = _('Description') )
	sequence = models.PositiveSmallIntegerField( default = 0, verbose_name = _('Sequence') )
	
	def save( self, *args, **kwargs ):
		init_sequence( Category, self )
		return super( Category, self ).save( *args, **kwargs )
	
	def make_copy( self, category_format ):
		category_new = self
		
		category_new.pk = None
		category_new.format = category_format
		category_new.save()
		return category_new
	
	def full_name( self ):
		return ', '.join( [self.code, self.get_gender_display(), self.description] )
		
	def get_search_text( self ):
		return utils.normalizeSearch(' '.join( u'"{}"'.format(f) for f in [self.code, self.get_gender_display(), self.description] ) )
		
	def __unicode__( self ):
		return u'{} ({}) [{}]'.format(self.code, self.description, self.format.name)
		
	@property
	def code_gender( self ):
		return u'{} ({})'.format(self.code, self.get_gender_display())
	
	class Meta:
		verbose_name = _('Category')
		verbose_name_plural = _("Categories")
		ordering = ['sequence', '-gender', 'code']

#---------------------------------------------------------------------------------

class Discipline(models.Model):
	name = models.CharField( max_length = 64 )
	sequence = models.PositiveSmallIntegerField( verbose_name = _('Sequence'), default = 0 )
	
	def save( self, *args, **kwargs ):
		init_sequence( Discipline, self )
		return super( Discipline, self ).save( *args, **kwargs )
	
	def __unicode__( self ):
		return self.name
		
	class Meta:
		verbose_name = _('Discipline')
		verbose_name_plural = _('Disciplines')
		ordering = ['sequence', 'name']

class RaceClass(models.Model):
	name = models.CharField( max_length = 64 )
	sequence = models.PositiveSmallIntegerField( verbose_name = _('Sequence'), default = 0 )
	
	def save( self, *args, **kwargs ):
		init_sequence( RaceClass, self )
		return super( RaceClass, self ).save( *args, **kwargs )
	
	def __unicode__( self ):
		return self.name

	class Meta:
		verbose_name = _('Race Class')
		verbose_name_plural = _('Race Classes')
		ordering = ['sequence', 'name']

class NumberSet(models.Model):
	name = models.CharField( max_length = 64, verbose_name = _('Name') )
	sequence = models.PositiveSmallIntegerField( db_index = True, verbose_name=_('Sequence'), default = 0 )

	def save( self, *args, **kwargs ):
		init_sequence( NumberSet, self )
		return super( NumberSet, self ).save( *args, **kwargs )
	
	def __unicode__( self ):
		return self.name
	
	class Meta:
		verbose_name = _('Number Set')
		verbose_name_plural = _('Number Sets')
		ordering = ['sequence']

#-------------------------------------------------------------------
class SeasonsPass(models.Model):
	name = models.CharField( max_length = 64, verbose_name = _('Name') )
	sequence = models.PositiveSmallIntegerField( db_index = True, verbose_name=_('Sequence'), default = 0 )

	def save( self, *args, **kwargs ):
		init_sequence( SeasonsPass, self )
		return super( SeasonsPass, self ).save( *args, **kwargs )
	
	def __unicode__( self ):
		return self.name
		
	def clone( self ):
		name_new = None
		for i in xrange(1, 1000):
			name_new = u'{} Copy({})'.format( self.name.split( ' Copy(' )[0], i )
			if not SeasonsPass.objects.exists( name = name_new ):
				break
		seasons_pass_new = SeasonsPass( name = name_new )
		seasons_pass_new.save()
		for sph in SeasonsPass.objects.filter( seasons_pass = self ):
			sph.seasons_pass = seasons_pass_new
			sph.save()
		return seasons_pass_new
	
	class Meta:
		verbose_name = _("Season's Pass")
		verbose_name_plural = _("Season's Passes")
		ordering = ['sequence']

class SeasonsPassHolder(models.Model):
	seasons_pass = models.ForeignKey( 'SeasonsPass', db_index = True, verbose_name = _("Season's Pass") )
	license_holder = models.ForeignKey( 'LicenseHolder', unique = True, db_index = True, verbose_name = _("LicenseHolder") )
	
	def __unicode__( self ):
		return u''.join( [unicode(self.seasons_pass), u': ', unicode(self.license_holder)] )
	
	class Meta:
		ordering = ['license_holder__search_text']
		verbose_name = _("Season's Pass Holder")
		verbose_name_plural = _("Season's Pass Holders")

#-------------------------------------------------------------------
class Competition(models.Model):
	name = models.CharField( max_length = 64, verbose_name = _('Name') )
	description = models.CharField( max_length = 80, default = '', blank = True, verbose_name=_('Description') )
	
	number_set = models.ForeignKey( NumberSet, blank=True, null=True, on_delete=models.SET_NULL, verbose_name=_('Number Set') )
	seasons_pass = models.ForeignKey( SeasonsPass, blank=True, null=True, on_delete=models.SET_NULL, verbose_name=_("Season's Pass") )
	
	city = models.CharField( max_length = 64, blank = True, default = '', verbose_name=_('City') )
	stateProv = models.CharField( max_length = 64, blank = True, default = '', verbose_name=_('StateProv') )
	country = models.CharField( max_length = 64, blank = True, default = '', verbose_name=_('Country') )
	
	category_format = models.ForeignKey(
		'CategoryFormat',
		verbose_name=_('Category Format') )
	
	organizer = models.CharField( max_length = 64, verbose_name=_('Organizer') )
	organizer_contact = models.CharField( max_length = 64, blank = True, default = '', verbose_name=_('Organizer Contact') )
	organizer_email = models.EmailField( blank = True, verbose_name=_('Organizer Email') )
	organizer_phone = models.CharField( max_length = 22, blank = True, default = '', verbose_name=_('Organizer Phone') )
	
	start_date = models.DateField( db_index = True, verbose_name=_('Start Date') )
	number_of_days = models.PositiveSmallIntegerField( default = 1, verbose_name = _('Number of Days') )
	
	discipline = models.ForeignKey( Discipline, verbose_name=_("Discipline") )
	race_class = models.ForeignKey( RaceClass, verbose_name=_("Race Class") )
	
	using_tags = models.BooleanField( default = False, verbose_name = _("Using Tags/Chip Reader") )
	use_existing_tags = models.BooleanField( default = True, verbose_name = _("Use Competitor's Existing Tags") )
	
	DISTANCE_UNIT_CHOICES = (
		(0, _('km')),
		(1, _('miles')),
	)
	distance_unit = models.PositiveSmallIntegerField(choices=DISTANCE_UNIT_CHOICES, default = 0, verbose_name = _('Distance Unit') )
	
	@property
	def speed_unit_display( self ):
		return 'km/h' if self.distance_unit == 0 else 'mph'
		
	def to_local_speed( self, kmh ):
		return kmh if self.distance_unit == 0 else kmh * 0.621371
		
	def to_kmh( self, speed ):
		return speed if self.distance_unit == 0 else speed / 0.621371
	
	def save(self, *args, **kwargs):
		''' If the start_date has changed, automatically update all the event dates too. '''
		if self.pk:
			try:
				competition_original = Competition.objects.get( pk = self.pk )
			except Exception as e:
				competition_original = None
			if competition_original and competition_original.start_date != self.start_date:
				time_delta = (
					datetime.datetime.combine(self.start_date, datetime.time(0,0,0)) -
					datetime.datetime.combine(competition_original.start_date, datetime.time(0,0,0))
				)
				self.adjust_event_times( time_delta )
			
		return super(Competition, self).save(*args, **kwargs)
	
	@transaction.atomic
	def make_copy( self ):
		category_numbers = self.categorynumbers_set.all()
		event_mass_starts = self.eventmassstart_set.all()
		event_tts = self.eventtt_set.all()
	
		competition_new = self
		competition_new.pk = None
		competition_new.start_date = datetime.date.today()
		competition_new.save()
		
		for cn in category_numbers:
			cn.make_copy( competition_new )
		for e in event_mass_starts:
			e.make_copy( competition_new )
		for e in event_tts:
			e.make_copy( competition_new )
		
		return competition_new
		
	def adjust_event_times( self, time_delta ):
		for e in self.eventmassstart_set.all():
			e.date_time += time_delta
			e.save()
	
	@property
	def finish_date( self ):
		return self.start_date + datetime.timedelta( days = self.number_of_days - 1 )
	
	@property
	def date_range_str( self ):
		sd = self.start_date
		ed = self.finish_date
		if sd == ed:
			return sd.strftime('%b %d, %Y')
		if sd.month == ed.month and sd.year == ed.year:
			return u'{}-{}'.format( sd.strftime('%b %d'), ed.strftime('%d, %Y') )
		if sd.year == ed.year:
			return u'{}-{}'.format( sd.strftime('%b %d'), ed.strftime('%b %d, %Y') )
		return u'{}-{}'.format( sd.strftime('%b %d, %Y'), ed.strftime('%b %d, %Y') )
	
	def full_name( self ):
		return ' '.join( [self.name, self.organizer] )
		
	def get_search_text( self ):
		return utils.get_search_text( [self.name, self.organizer] )
	
	def get_events_mass_start( self ):
		return EventMassStart.objects.filter(competition = self).order_by('date_time')
		
	def get_events_tt( self ):
		return EventTT.objects.filter(competition = self).order_by('date_time')
		
	def get_events( self ):
		return list(self.get_events_mass_start()) + list(self.get_events_tt())
		
	def get_categories( self ):
		return Category.objects.filter( format = self.category_format )
	
	#----------------------------------------------------------------------------------------------------

	def get_categories_with_numbers( self ):
		category_lookup = set( c.id for c in Category.objects.filter(format = self.category_format) )
		categories = []
		for cn in self.categorynumbers_set.all():
			categories.extend( list(c for c in cn.categories.all() if c.id in category_lookup) )
		return sorted( set(categories), key = lambda c: c.sequence )
		return categories
	
	def get_categories_without_numbers( self ):
		categories_all = set( c for c in Category.objects.filter(format = self.category_format) )
		categories_with_numbers = set( self.get_categories_with_numbers() )
		categories_without_numbers = categories_all - categories_with_numbers
		return sorted( categories_without_numbers, key = lambda c: c.sequence )
	
	def get_category_numbers( self, category ):
		for cn in CategoryNumbers.objects.filter( competition = self, categories__in = [category] ):
			return cn
		return None
	
	#----------------------------------------------------------------------------------------------------

	def competition_age( self, license_holder ):
		# For cyclocross races between September and December,
		# use the next year as the competition age, not the current year.
		age = self.start_date.year - license_holder.date_of_birth.year
		if 'cyclo' in self.discipline.name.lower() and 9 <= self.start_date.month <= 12:
			age += 1
		return age
	
	def get_participant_events( self, participant ):
		participant_events = []
		for events in (self.eventmassstart_set.all(), self.eventtt_set.all()):
			for event in events:
				if event.could_participate(participant):
					participant_events.append( (event, event.is_optional, event.is_participating(participant)) )
		return participant_events
	
	class Meta:
		verbose_name = _('Competition')
		verbose_name_plural = _('Competitions')
		ordering = ['-start_date', 'name']

class CategoryNumbers( models.Model ):
	competition = models.ForeignKey( Competition, db_index = True )
	categories = models.ManyToManyField( Category )
	range_str = models.TextField( default = '1-99,120-129,-50-60,181,-87', verbose_name=_('Range') )
	
	numCache = None
	valid_chars = set( u'0123456789,-' )
	numMax = 99999
	
	@property
	def category_list( self ):
		return u', '.join( c.code for c in self.get_category_list() )
	
	def get_category_list( self ):
		return sorted( self.categories.all(), key = lambda c: c.sequence )
	
	def get_key( self ):
		try:
			return min( c.sequence for c in self.categories.all() )
		except ValueError:
			return -1
	
	def make_copy( self, competition_new ):
		categories = self.categories.all()
		
		category_numbers_new = self
		category_numbers_new.pk = None
		category_numbers_new.competition = competition_new
		category_numbers_new.save()
		
		category_numbers_new.categories = categories
		return category_numbers_new
	
	def normalize( self ):
		# Normalize the input.
		r = self.range_str.replace( u' ', u',' ).replace( u'\n', u',' )
		r = u''.join( v for v in r if v in self.valid_chars )
		while 1:
			rNew = r.replace( ',,', ',' ).replace( '--', '-' ).replace( '-,', ',' )
			if rNew == r:
				break
			r = rNew
		if r.startswith( ',' ):
			r = r[1:]
		while r.endswith( ',' ) or r.endswith( '-' ):
			r = r[:-1]
		
		pairs = []
		for p in r.split( u',' ):
			p = p.strip()
			if p.startswith( '-' ):
				exclude = u'-'
				p = p[1:]
			else:
				exclude = u''
				
			pair = p.split( u'-' )
			if len(pair) == 1:
				try:
					n = int(pair[0])
				except:
					continue
				pairs.append( exclude + unicode(n) )
			elif len(pair) >= 2:
				try:
					nBegin = int(pair[0])
				except:
					continue
				try:
					nEnd = int(pair[1])
				except:
					continue
				nBegin = min( nBegin, self.numMax )
				nEnd = min( max(nBegin,nEnd), self.numMax )
				pairs.append( exclude + unicode(nBegin) + u'-' + unicode(nEnd) )
		
		self.range_str = u', '.join( pairs )
	
	def getNumbersWorker( self ):
		self.normalize()
		
		include = set()
		for p in self.range_str.split( ',' ):
			p = p.strip()
			
			if p.startswith( '-' ):
				exclude = True
				p = p[1:]
			else:
				exclude = False
				
			pair = p.split( '-' )
			if len(pair) == 1:
				n = int(pair[0])
				if exclude:
					include.discard( n )
				else:
					include.add( n )
			else:
				nBegin, nEnd = [int(v) for v in pair[:2]]
				nEnd = min( nEnd, 10000 )
				if exclude:
					include.difference_update( xrange(nBegin, nEnd+1) )
				else:
					include.update( xrange(nBegin, nEnd+1) )
		self.numbers = include
		return include
	
	def get_numbers( self ):
		if self.numCache is None or self.range_str_cache != self.range_str:
			self.numCache = self.getNumbersWorker()
			self.range_str_cache = self.range_str
		return self.numCache
	
	def __contains__( self, n ):
		return n in self.getNumbers()
		
	def add_bib( self, n ):
		if n not in self:
			self.range_str += u', {}'.format( n )
			
	def remove_bib( self, n ):
		if n in self:
			self.range_str += u', -{}'.format( n )
		
	def save(self, *args, **kwargs):
		self.normalize()
		return super(CategoryNumbers, self).save( *args, **kwargs )
		
	class Meta:
		verbose_name = _('CategoryNumbers')
		verbose_name_plural = _('CategoriesNumbers')

class Event( models.Model ):
	competition = models.ForeignKey( Competition, db_index = True )
	name = models.CharField( max_length = 80, verbose_name=_('Name') )
	date_time = models.DateTimeField( db_index = True, verbose_name=_('Date Time') )
	
	EVENT_TYPE_CHOICES = (
		(0, _('Mass Start')),
		(1, _('Time Trial')),
		#(2, _('Sprint')),
	)
	event_type = models.PositiveSmallIntegerField( choices=EVENT_TYPE_CHOICES, default = 0, verbose_name = ('Event Type') )
	
	optional = models.BooleanField( default=False, verbose_name=_('Optional'),
		help_text=_('Allows Participants to choose to enter.  Otherwise the Event is included for all participants.') )
	option_id = models.PositiveIntegerField( default=0, verbose_name = _('Option Id') )
	select_by_default = models.BooleanField( default=False, verbose_name=_('Select by Default'),
		help_text=_('If the event is Optional, Participants will be automatically added to the event, but can opt-out later.') )
	
	RFID_OPTION_CHOICES = (
		(0, _('Manual Start: Collect every chip. Does NOT restart race clock on first read.')),
		(1, _('Automatic Start: Reset start clock on first tag read.  All riders get the start time of the first read.')),
		(2, _('Manual Start: Skip first tag read for all riders.  Required when start run-up passes the finish line.')),
	)
	rfid_option = models.PositiveIntegerField( choices=RFID_OPTION_CHOICES, default=1, verbose_name = _('RFID Option') )
	
	@property
	def is_optional( self ):
		return self.option_id != 0
	
	def save( self, *args, **kwargs ):
		if not self.optional and self.option_id:
			ParticipantOption.delete_option_id( self.competition, self.option_id )
			self.option_id = 0
		super( Event, self ).save( *args, **kwargs )
		if self.optional and not self.option_id:
			ParticipantOption.set_event_option_id( self.competition, self )
	
	def get_wave_set( self ):
		try:
			return self.wave_set
		except AttributeError:
			return self.wavett_set

	def reg_is_late( self, reg_closure_minutes, registration_timestamp ):
		if reg_closure_minutes < 0:
			return False
		delta = self.date_time - registration_timestamp
		return delta.total_seconds()/60.0 < reg_closure_minutes
	
	def make_copy( self, competition_new ):
		time_diff = self.date_time - datetime.datetime.combine(self.competition.start_date, datetime.time(0,0,0)).replace(tzinfo = get_default_timezone())
		waves = self.get_wave_set().all()
		
		event_mass_start_new = self
		event_mass_start_new.pk = None
		event_mass_start_new.competition = competition_new
		event_mass_start_new.date_time = datetime.datetime.combine(competition_new.start_date, datetime.time(0,0,0)).replace(tzinfo = get_default_timezone()) + time_diff
		event_mass_start_new.save()
		for w in waves:
			w.make_copy( event_mass_start_new )
		return event_mass_start_new
	
	def get_duplicate_bibs( self ):
		duplicates = []
		for w in self.get_wave_set().all():
			bibParticipant = {}
			for c in w.categories.all():
				for p in Participant.objects.filter( competition = self.competition, category = c, bib__isnull = False ):
					if p.bib in bibParticipant:
						duplicates.append( _('{}: {} ({}) and {} ({}) have duplicate Bib {}').format(
							w.name,
							bibParticipant[p.bib].name, bibParticipant[p.bib].category.code,
							p.name, p.category.code, p.bib) )
					else:
						bibParticipant[p.bib] = p
		return duplicates
		
	#----------------------------------------------------------------------------------------------------
	
	def get_potential_duplicate_bibs( self ):
		categories = set()
		for w in self.get_wave_set().all():
			categories |= set( w.categories.all() )
				
		category_numbers = set()
		for c in categories:
			for cn in CategoryNumbers.objects.filter( competition=self.competition, categories__in=[c] ):
				category_numbers.add( cn )
		
		potential_duplicates = []
		category_numbers = list( category_numbers )
		for i, cnLeft in enumerate(category_numbers):
			numbersLeft = cnLeft.get_numbers()
			for cnRight in category_numbers[i+1:]:
				numbersRight = cnRight.get_numbers()
				numbersConflict = numbersLeft & numbersRight
				if numbersConflict:
					potential_duplicates.append( (
						u', '.join( c.code for c in cnLeft.categories.all() ),
						u', '.join( c.code for c in cnRight.categories.all() ),
						sorted(numbersConflict)
					))						
		return potential_duplicates

	def get_categories_with_wave( self ):
		category_lookup = set( c.id for c in Category.objects.filter(format = self.competition.category_format) )
		categories = []
		for wave in self.get_wave_set().all():
			categories.extend( list(c for c in wave.categories.all() if c.id in category_lookup) )
		return sorted( set(categories), key = lambda c: c.sequence )
	
	def get_categories_without_wave( self ):
		categories_all = set( c for c in Category.objects.filter(format = self.competition.category_format) )
		categories_with_wave = set( self.get_categories_with_wave() )
		categories_without_wave = categories_all - categories_with_wave
		return sorted( categories_without_wave, key = lambda c: c.sequence )
	
	def get_participant_count( self ):
		return sum( w.get_participant_count() for w in self.get_wave_set().all() )

	def get_late_reg_exists( self ):
		return any( w.get_late_reg().exists() for w in self.get_wave_set().all() )
		
	def could_participate( self, participant ):
		return participant.category and any( w.could_participate(participant) for w in self.get_wave_set().all() )
		
	def is_participating( self, participant ):
		return participant.category and any( w.is_participating(participant) for w in self.get_wave_set().all() )
		
	@property
	def wave_text( self ):
		return u', '.join( u'{} ({})'.format(w.name, w.category_text) for w in self.get_wave_set().all() )
	
	@property
	def wave_text_line_html( self ):
		return u', '.join( u'<strong>{}</strong> {}'.format(w.name, w.category_text) for w in self.get_wave_set().all() )
	
	@property
	def wave_text_html( self ):
		return u'<ol><li>' + u'</li><li>'.join( u'<strong>{}</strong>:&nbsp;&nbsp;{}'.format(w.name, w.category_text) for w in self.get_wave_set().all() ) + u'</li></ol>'
	
	def get_participants( self ):
		participants = set()
		for w in self.get_wave_set().all():
			participants |= set( w.get_participants_unsorted().select_related('competition','license_holder','team') )
		return participants
	
	def __unicode__( self ):
		return u'%s, %s (%s)' % (self.date_time, self.name, self.competition.name)
	
	@property
	def short_name( self ):
		return u'{} ({})'.format( self.name, {0:_('Mass'), 1:_('TT')}.get(self.event_type,u'') )
	
	class Meta:
		verbose_name = _('Event')
		verbose_name_plural = _('Events')
		ordering = ['date_time']
		abstract = True

#---------------------------------------------------------------------------------------------------------

class EventMassStart( Event ):
	
	class Meta:
		verbose_name = _('Mass Start Event')
		verbose_name_plural = _('Mass Starts Event')

class WaveBase( models.Model ):
	name = models.CharField( max_length = 32 )
	categories = models.ManyToManyField( Category, verbose_name = _('Categories') )
	
	distance = models.FloatField( null = True, blank = True, verbose_name = _('Distance') )
	laps = models.PositiveSmallIntegerField( null = True, blank = True, verbose_name = _('Laps') )
	
	@property
	def distance_unit( self ):
		return self.event.competition.get_distance_unit_display() if self.event else ''
	
	def get_category_format( self ):
		return self.event.competition.category_format
	
	def make_copy( self, event_new ):
		categories = self.categories.all()
		wave_new = self
		wave_new.pk = None
		wave_new.event = event_new
		wave_new.save()
		wave_new.categories = categories
		return wave_new
	
	def get_potential_duplicate_bibs( self ):
		if not self.id:
			return []
		competition = self.event.competition
		
		other_categories = set()
		my_categories = set()
		
		for w in self.event.get_wave_set().all():
			if w != self:
				other_categories |= set( w.categories.all() )
			else:
				my_categories |= set( w.categories.all() )
		
		other_category_numbers = set()
		my_category_numbers = set()
		for cn in self.event.competition.categorynumbers_set.all():
			categories_cur = list( cn.categories.all() )
			if any( c in other_categories for c in categories_cur ):
				other_category_numbers.add( cn )
			if any( c in my_categories for c in categories_cur ):
				my_category_numbers.add( cn )
		
		other_bibs = set.union( *[c.get_numbers() for c in other_category_numbers] ) if other_category_numbers else set()
		my_bibs = set.union( *[c.get_numbers() for c in my_category_numbers] ) if my_category_numbers else set()
		
		return sorted( other_bibs & my_bibs )
	
	def get_participants_unsorted( self ):
		if not self.event.option_id:
			return Participant.objects.filter(
				competition=self.event.competition,
				category__in=self.categories.all(),
			)
		else:
			return Participant.objects.filter(
				competition=self.event.competition,
				category__in=self.categories.all(),
				pk__in=ParticipantOption.objects.filter(
							competition=self.event.competition,
							option_id=self.event.option_id,
						).values_list('participant__pk', flat=True)
			)
	
	def get_participants( self ):
		return self.get_participants_unsorted().select_related('competition','license_holder','team').order_by('bib')
	
	def get_participant_count( self ):
		return self.get_participants_unsorted().count()
		
	def could_participate( self, participant ):
		return participant.category and self.categories.filter(pk=participant.category.pk).exists()
	
	def is_participating( self, participant ):
		return (not self.event.option_id or
					ParticipantOption.objects.filter(
						competition=self.event.competition,
						participant=participant,
						option_id=self.event.option_id).exists()) and self.could_participate(participant)
	
	def reg_is_late( self, reg_closure_minutes, registration_timestamp ):
		return self.event.reg_is_late( reg_closure_minutes, registration_timestamp )
	
	def get_late_reg( self ):
		latest_reg_timestamp = self.event.date_time - datetime.timedelta( seconds=SystemInfo.get_reg_closure_minutes()*60 )
		return self.get_participants_unsorted().filter( registration_timestamp__gt=latest_reg_timestamp )
	
	def get_late_reg_set( self ):
		return set( self.get_late_reg() )
	
	def get_late_reg_count( self ):
		return self.get_late_reg().count()
	
	@property
	def category_text( self ):
		return u', '.join( category.code_gender for category in sorted(self.categories.all(), key=lambda c: c.sequence) )
	
	@property
	def category_text_html( self ):
		return u'<ol><li>' + u'</li><li>'.join( category.code_gender for category in sorted(self.categories.all(), key=lambda c: c.sequence) ) + u'</li></ol>'
	
	class Meta:
		verbose_name = _('Wave Base')
		verbose_name_plural = _('Wave Bases')
		abstract = True

class Wave( WaveBase ):
	event = models.ForeignKey( EventMassStart, db_index = True )
	start_offset = DurationField( default = 0, verbose_name = _('Start Offset') )
	
	minutes = models.PositiveSmallIntegerField( null = True, blank = True, verbose_name = _('Race Minutes') )
	
	def get_start_time( self ):
		return self.event.date_time + self.start_offset
	
	class Meta:
		verbose_name = _('Wave')
		verbose_name_plural = _('Waves')
		ordering = ['start_offset', 'name']

class WaveCallup( models.Model ):
	wave = models.ForeignKey( Wave, db_index = True )
	participant = models.ForeignKey( 'Participant', db_index = True )
	order = models.PositiveSmallIntegerField( blank = True, default = 9999, verbose_name = _('Callup Order') )
	
	class Meta:
		verbose_name = _('WaveCallup')
		verbose_name_plural = _('WaveCallups')
		ordering = ['order']
	
#-------------------------------------------------------------------------------------
class Team(models.Model):
	name = models.CharField( max_length = 64, db_index = True, verbose_name = _('Name') )
	team_code = models.CharField( max_length = 3, blank = True, db_index = True, verbose_name = _('Team Code') )
	TYPE_CHOICES = (
		(0, _('Club')),
		(1, _('Regional')),
		(2, _('Mixed')),
		(3, _('National')),
		(4, _('UCI Women')),
		(5, _('UCI Continental')),
		(6, _('UCI Pro Continental')),
		(7, _('UCI Pro')),
	)
	team_type = models.PositiveSmallIntegerField(choices=TYPE_CHOICES, default = 0, verbose_name = _('Type') )
	nation_code = models.CharField( max_length=3, blank = True, default='', verbose_name = _('Nation Code') )
	
	active = models.BooleanField( default = True, verbose_name = _('Active') )
	
	was_team = models.OneToOneField('self', blank=True, null=True, on_delete=models.SET_NULL,
					related_name='is_now_team', verbose_name = _('Was Team'))
					
	SearchTextLength = 80
	search_text = models.CharField( max_length=SearchTextLength, blank=True, default='', db_index=True )

	def save( self, *args, **kwargs ):
		self.search_text = self.get_search_text()[:self.SearchTextLength]
		return super(Team, self).save( *args, **kwargs )
	
	def full_name( self ):
		fields = [self.name, self.team_code, self.get_team_type_display(), self.nation_code]
		return u', '.join( f for f in fields if f )
	
	def get_search_text( self ):
		return utils.get_search_text( [self.name, self.team_code, self.get_team_type_display(), self.nation_code] )
	
	def short_name( self ):
		return self.name
		
	def unicode( self ):
		return u'{}, {}'.format(self.name, self.team_type_display())
	
	class Meta:
		verbose_name = _('Team')
		verbose_name_plural = _('Teams')
		ordering = ['search_text']

class LicenseHolder(models.Model):
	last_name = models.CharField( max_length=64, verbose_name=_('Last Name'), db_index=True )
	first_name = models.CharField( max_length=64, verbose_name=_('First Name'), db_index=True )
	
	GENDER_CHOICES=(
		(0, _('Men')),
		(1, _('Women')),
	)
	gender = models.PositiveSmallIntegerField( choices=GENDER_CHOICES, default=0 )
	
	date_of_birth = models.DateField()
	
	city = models.CharField( max_length=64, blank=True, default='', verbose_name=_('City') )
	state_prov = models.CharField( max_length=64, blank=True, default='', verbose_name=_('State/Prov') )
	nationality = models.CharField( max_length=64, blank=True, default='', verbose_name=_('Nationality') )
	
	email = models.EmailField( blank=True )
	
	uci_code = models.CharField( max_length=11, blank=True, default='', db_index=True, verbose_name=_('UCI Code') )
	
	license_code = models.CharField( max_length=32, null=True, unique=True, verbose_name=_('License Code') )
	
	existing_bib = models.PositiveSmallIntegerField( null=True, blank=True, db_index=True, verbose_name=_('Existing Bib') )
	
	existing_tag = models.CharField( max_length=36, null=True, blank=True, unique=True, verbose_name=_('Existing Tag') )
	existing_tag2 = models.CharField( max_length=36, null=True, blank=True, unique=True, verbose_name=_('Existing Tag2') )
	
	suspended = models.BooleanField( default=False, verbose_name=_('Suspended'), db_index=True )
	active = models.BooleanField( default=True, verbose_name=_('Active'), db_index=True )

	SearchTextLength = 256
	search_text = models.CharField( max_length=SearchTextLength, blank=True, default='', db_index=True )

	def save( self, *args, **kwargs ):
		self.uci_code = (self.uci_code or '').strip().upper()
		if len(self.uci_code) == 3:
			self.uci_code += self.date_of_birth.strftime( '%Y%m%d' )
			
		for f in ['last_name', 'first_name', 'city', 'state_prov', 'nationality', 'uci_code']:
			setattr( self, f, (getattr(self, f) or '').strip() )
		
		if not self.uci_code and self.nationality:
			try:
				country = iso3166.countries.get( self.nationality )
				self.uci_code = '{}{}'.format( country.alpha3, self.date_of_birth.strftime('%Y%m%d') )
			except KeyError:
				pass
		
		for f in ['license_code', 'existing_tag', 'existing_tag2']:
			setattr( self, f, fixNullUpper(getattr(self, f)) )
			
		self.search_text = self.get_search_text()[:self.SearchTextLength]
		
		super(LicenseHolder, self).save( *args, **kwargs )
		
		# If the license_code is TEMP, add the record id to make it a unique temporary code.
		if self.license_code == u'TEMP':
			self.license_code = u'TEMP{}'.format( self.id )
			self.search_text = self.get_search_text()[:self.SearchTextLength]
			super(LicenseHolder, self).save( *args, **kwargs )

	def __unicode__( self ):
		return '%s, %s (%s, %s, %s, %s)' % (
			self.last_name.upper(), self.first_name,
			self.date_of_birth.isoformat(), self.get_gender_display(),
			self.uci_code, self.license_code
		)
		
	def full_name( self ):
		return u"{}, {}".format(self.last_name.upper(), self.first_name)
		
	def full_license( self ):
		return u', '.join( f for f in [self.uci_code, self.license_code] if f )
		
	def get_location( self ):
		return u', '.join( f for f in [self.city, get_abbrev(self.state_prov)] if f )
		
	def get_search_text( self ):
		return utils.get_search_text( [
				self.last_name, self.first_name,
				self.license_code, self.uci_code,
				self.nationality, self.state_prov, self.city,
				self.existing_tag, self.existing_tag2
			]
		)
		
	def get_unique_tag( self ):
		system_info = SystemInfo.get_singleton()
		return getTagFormatStr( system_info.tag_template ).format( n=self.id )
	
	def get_existing_tag_str( self ):
		return u', '.join( [t for t in [self.existing_tag, self.existing_tag2] if t] )
	
	def get_participation_as_competitor( self ):
		return Participant.objects.select_related('competition', 'team', 'category').filter(
			license_holder=self, role=Participant.Competitor, category__isnull=False
		).order_by( '-competition__start_date' )
	
	def get_tt_metric( self, ref_date ):
		years = (self.date_of_birth - ref_date).days / 365.26
		dy = years - 24.0	# Fastest estimated year.
		if dy < 0:
			dy *= 4
		return -(dy ** 2)
	
	class Meta:
		verbose_name = _('LicenseHolder')
		verbose_name_plural = _('LicenseHolders')
		ordering = ['search_text']

class TeamHint(models.Model):
	license_holder = models.ForeignKey( 'LicenseHolder', db_index = True )
	discipline = models.ForeignKey( 'Discipline', db_index = True )
	team = models.ForeignKey( 'Team', db_index = True )
	effective_date = models.DateField( verbose_name = _('Effective Date'), db_index = True )
	
	def unicode( self ):
		return unicode(license_holder) + ' ' + unicode(discipline) + ' ' + unicode(team) + ' ' + unicode(effective_date)
	
	class Meta:
		verbose_name = _('TeamHint')
		verbose_name_plural = _('TeamHints')
		
class CategoryHint(models.Model):
	license_holder = models.ForeignKey( 'LicenseHolder', db_index = True )
	discipline = models.ForeignKey( 'Discipline', db_index = True )
	category = models.ForeignKey( 'Category', db_index = True )
	effective_date = models.DateField( verbose_name = _('Effective Date'), db_index = True )
	
	def unicode( self ):
		return unicode(license_holder) + ' ' + unicode(discipline) + ' ' + unicode(category) + ' ' + unicode(effective_date)
	
	class Meta:
		verbose_name = _('CategoryHint')
		verbose_name_plural = _('CategoryHints')

class NumberSetEntry(models.Model):
	number_set = models.ForeignKey( 'NumberSet', db_index = True )
	license_holder = models.ForeignKey( 'LicenseHolder', db_index = True )
	bib = models.PositiveSmallIntegerField( db_index = True, verbose_name=_('Bib') )
	
	class Meta:
		verbose_name = _('NumberSetEntry')
		verbose_name_plural = _('NumberSetEntries')
		
class FormatTimeDelta( datetime.timedelta ):
	def __repr__( self ):
		fraction, seconds = math.modf( self.total_seconds() )
		seconds = int(seconds)
		return '%d:%02d:%02.3f' % (seconds // (60*60), (seconds // 60) % 60, seconds % 60 + fraction)
	
	def __unicode( self ):
		return unicode( self.__repr__() )
		
class Participant(models.Model):
	competition = models.ForeignKey( 'Competition', db_index=True )
	license_holder = models.ForeignKey( 'LicenseHolder', db_index=True )
	team = models.ForeignKey( 'Team', null=True, db_index=True, on_delete=models.SET_NULL  )
	
	ROLE_NAMES = ( '',	# No zero code.
		_('Team'), _('Official'), _('Organizer')
	)
	Competitor = 110
	COMPETITION_ROLE_CHOICES = (
		(_('Team'), (
			(Competitor, _('Competitor')),
			(120, _('Manager')),
			(130, _('Coach')),
			(140, _('Doctor')),
			(150, _('Paramedical Asst.')),
			(160, _('Mechanic')),
			(170, _('Driver')),
			(199, _('Team Staff')),
			)
		),
		(_('Official'), (
			(210, _('Commissaire')),
			(220, _('Timer')),
			(230, _('Announcer')),
			(240, _('Radio Operator')),
			(250, _('Para Classifier')),
			(299, _('Official Staff')),
			)
		),
		(_('Organizer'), (
			(310, _('Administrator')),
			(320, _('Mechanic')),
			(330, _('Driver')),
			(399, _('Organizer Staff')),
			)
		),
	)
	role=models.PositiveSmallIntegerField( choices=COMPETITION_ROLE_CHOICES, default=110, verbose_name=_('Role') )
	
	preregistered=models.BooleanField( default=False, verbose_name=_('Preregistered') )
	
	registration_timestamp=models.DateTimeField( auto_now_add=True )
	category=models.ForeignKey( 'Category', null=True, blank=True, db_index=True )
	
	bib=models.PositiveSmallIntegerField( null=True, blank=True, db_index=True, verbose_name=_('Bib') )
	
	tag=models.CharField( max_length=36, null=True, blank=True, verbose_name=_('Tag') )
	tag2=models.CharField( max_length=36, null=True, blank=True, verbose_name=_('Tag2') )

	signature=models.TextField( blank=True, default='', verbose_name=_('Signature') )

	paid=models.BooleanField( default=False, verbose_name=_('Paid') )
	confirmed=models.BooleanField( default=False, verbose_name=_('Confirmed') )
	
	note=models.TextField( blank=True, default='', verbose_name=_('Note') )
	
	est_kmh=models.FloatField( default=0.0, verbose_name=_('Est Kmh') )
	
	@property
	def est_speed_display( self ):
		return u'{:g} {}'.format( self.competition.to_local_speed(self.est_kmh), self.competition.speed_unit_display )
	
	def save( self, *args, **kwargs ):
		competition = self.competition
		license_holder = self.license_holder
		
		for f in ['signature', 'note']:
			setattr( self, f, (getattr(self, f) or '').strip() )
		
		for f in ['tag', 'tag2']:
			setattr( self, f, fixNullUpper(getattr(self, f)) )
		
		if self.role == self.Competitor:
			if competition.number_set:
				if self.bib:
					try:
						nse = NumberSetEntry.objects.get( number_set=competition.number_set, license_holder=license_holder )
						if nse.bib != self.bib:
							nse.bib = self.bib
							nse.save()
					except NumberSetEntry.DoesNotExist:
						NumberSetEntry( number_set=competition.number_set, license_holder=license_holder, bib=self.bib ).save()
				else:
					NumberSetEntry.objects.filter( number_set=competition.number_set, license_holder=license_holder ).delete()
				
			if license_holder.existing_tag != self.tag or license_holder.existing_tag2 != self.tag2:
				license_holder.existing_tag = self.tag
				license_holder.existing_tag2 = self.tag2
				license_holder.save()
				
		return super(Participant, self).save( *args, **kwargs )
	
	@property
	def roleCode( self ):
		return self.role // 100
		
	@property
	def is_with_team( self ):
		return 100 <= self.role <= 199
		
	@property
	def is_with_officials( self ):
		return 100 <= self.role <= 199
		
	@property
	def is_with_organizer( self ):
		return 100 <= self.role <= 199
		
	@property
	def is_competitor( self ):
		return self.role == Participant.Competitor
		
	@property
	def is_seasons_pass_holder( self ):
		return self.competition.seasons_pass and SeasonsPassHolder.objects.filter(seasons_pass=self.competition.seasons_pass, license_holder=self.license_holder).exists()

	@property
	def role_full_name( self ):
		return u'{} {}'.format( self.ROLE_NAMES[self.roleCode()], get_role_display() )
	
	@property
	def needs_bib( self ):
		return self.role == 1 and not self.bib
	
	@property
	def needs_tag( self ):
		return self.competition.using_tags and not self.tag and not self.tag2
	
	@property
	def name( self ):
		fields = [ getattr(self.license_holder, a) for a in ['first_name', 'last_name', 'uci_code', 'license_code'] ]
		if self.team:
			fields.append( self.team.short_name() )
		return u''.join( [u'{} '.format(self.bib) if self.bib else u'', u', '.join( [f for f in fields if f] )] )
	
	@property
	def full_name_team( self ):
		return u':  '.join( n for n in [self.license_holder.full_name(), self.team.name if self.team else None] if n )
	
	def __unicode__( self ):
		return self.name
	
	@transaction.atomic
	def add_to_default_optonal_events( self ):
		if self.category:
			for e in [event for event in competition.get_events() if event.select_by_default and event.could_participate(self)]:
				try:
					ParticipantOption( competition=e.competition, participant=participant, option_id=e.option_id ).save()
				except Exception as e:
					pass
	
	def init_default_values( self ):
		if self.competition.number_set:
			try:
				self.bib = NumberSetEntry.objects.get( number_set=self.competition.number_set, license_holder=self.license_holder ).bib
			except NumberSetEntry.DoesNotExist:
				pass
		
		if self.competition.use_existing_tags:
			self.tag  = self.license_holder.existing_tag
			self.tag2 = self.license_holder.existing_tag2
	
		def init_values( pp ):
			if not self.est_kmh and pp.competition.discipline==self.competition.discipline and pp.est_kmh:
				self.est_kmh = pp.est_kmh
			
			if not self.team and pp.team:
				team = pp.team
				while 1:
					try:
						team = team.is_now_team
					except ObjectDoesNotExist:
						break
				self.team = team
			if not self.role:
				self.role = pp.role
			if not self.category and pp.competition.category_format == self.competition.category_format:
				self.category = pp.category
			return self.team and self.role and self.category
	
		self.role = 0
		init_date = None
		for pp in sorted(	Participant.objects.filter(license_holder=self.license_holder),
							key = lambda x: (x.competition.start_date, -(x.category.sequence if x.category else 999999)),
							reverse = True ):
			if init_values(pp):
				init_date = pp.competition.start_date
				break
		#if not self.role:
		#	self.role = Participant._meta.get_field_by_name('role')[0].default

		# If we still don't have an est_kmh, try to get one from a previous competition of the same discipline.
		if not self.est_kmh:
			for est_kmh in Participant.objects.filter(
						license_holder=self.license_holder,
						competition__discipline=self.competition.discipline
					).exclude(
						est_kmh=0.0
					).order_by(
						'-competition__start_date'
					).values_list('est_kmh', flat=True):
				self.est_kmh = est_kmh
				break
		
		try:
			th = TeamHint.objects.get( license_holder=self.license_holder, discipline=self.competition.discipline )
			if init_date is None or th.effective_date > init_date:
				init_date = th.effective_date
				self.team = th.team
		except TeamHint.DoesNotExist:
			pass
		
		if self.is_seasons_pass_holder:
			self.paid = True
		
		self.role = Participant._meta.get_field_by_name('role')[0].default
		
		return self
	
	@property
	def show_confirm( self ):
		return	self.is_competitor and \
				self.bib and \
				self.category and \
				self.paid and \
				not self.needs_tag
		
	def auto_confirm( self ):
		if self.competition.start_date <= datetime.date.today() <= self.competition.finish_date and self.show_confirm:
			self.confirmed = True
		return self
	
	def get_other_category_participants( self ):
		return list(
					Participant.objects.filter(
						competition = self.competition,
						license_holder = self.license_holder,
						role = self.Competitor,
					).exclude( id=self.id )
				)
	
	def get_bib_conflicts( self ):
		if not self.bib:
			return []
		q = Q( competition = self.competition ) & Q( bib = self.bib )
		category_numbers = self.competition.get_category_numbers( self.category ) if self.category else None
		if category_numbers:
			q &= Q( category__in = category_numbers.categories.all() )
		return list( p for p in Participant.objects.filter(q) if p != self )
	
	def get_start_waves( self ):
		if not self.category:
			return []
		waves = sorted( Wave.objects.filter(event__competition=self.competition, categories=self.category), key=Wave.get_start_time )
		waves = [w for w in waves if w.is_participating(self)]
		reg_closure_minutes = SystemInfo.get_reg_closure_minutes()
		for w in waves:
			w.is_late = w.reg_is_late( reg_closure_minutes, self.registration_timestamp )
		return waves
	
	def get_start_wave_tts( self ):
		if not self.category:
			return []
		waves = sorted( WaveTT.objects.filter(event__competition=self.competition, categories=self.category), key=lambda w: w.sequence )
		waves = [w for w in waves if w.is_participating(self)]
		reg_closure_minutes = SystemInfo.get_reg_closure_minutes()
		for w in waves:
			w.is_late = w.reg_is_late( reg_closure_minutes, self.registration_timestamp )
		return waves
	
	def get_participant_events( self ):
		return self.competition.get_participant_events(self)
		
	def has_optional_events( self ):
		return any( optional for event, optional, entered in self.get_participant_events() )
		
	def has_tt_events( self ):
		return any( entered and event.event_type == 1 for event, optional, entered in self.get_participant_events() )
	
	def explain_integrity_error( self ):
		try:
			participant = Participant.objects.get(competition=self.competition, category=self.category, license_holder=self.license_holder)
			return True, _('This LicenseHolder is already in this Category'), participant
		except Participant.DoesNotExist:
			pass
			
		try:
			participant = Participant.objects.get(competition=self.competition, category=self.category, bib=self.bib)
			return True, _('A Participant is already in this Category with the same Bib.  Assign "No Bib" first, then try again.'), participant
		except Participant.DoesNotExist:
			pass
			
		try:
			participant = Participant.objects.get(competition=self.competition, category=self.category, tag=self.tag)
			return True, _('A Participant is already in this Category with the same Chip Tag.  Assign empty "Tag" first, and try again.'), participant
		except Participant.DoesNotExist:
			pass
			
		try:
			participant = Participant.objects.get(competition=self.competition, category=self.category, tag2=self.tag2)
			return True, _('A Participant is already in this Category with the same Chip Tag2.  Assign empty "Tag2" first, and try again.'), participant
		except Participant.DoesNotExist:
			pass
		
		return False, _('Unknown Integrity Error.'), None
	
	def get_tag_str( self ):
		return u', '.join( [t for t in [self.tag, self.tag2] if t] )
	
	class Meta:
		unique_together = (
			('competition', 'category', 'license_holder'),
			('competition', 'category', 'bib'),
			('competition', 'category', 'tag'),
			('competition', 'category', 'tag2'),
		)
		ordering = ['license_holder__search_text']
		verbose_name = _('Participant')
		verbose_name_plural = _('Participants')

#---------------------------------------------------------------------------------------------------------

class EntryTT( models.Model ):
	event = models.ForeignKey( 'EventTT', db_index = True, verbose_name=_('Event') )
	participant = models.ForeignKey( 'Participant', db_index = True, verbose_name=_('Participant') )
	
	est_speed = models.FloatField( default=0.0, verbose_name=_('Est. Speed') )
	hint_sequence = models.PositiveIntegerField( default=0, verbose_name = _('Hint Sequence') )
	
	start_sequence = models.PositiveIntegerField( default = 0, db_index = True, verbose_name = _('Start Sequence') )
	
	start_time = DurationField( null = True, blank = True, verbose_name=_('Start Time') )
	
	finish_time = DurationField( null = True, blank = True, verbose_name=_('Finish Time') )
	adjustment_time = DurationField( null = True, blank = True, verbose_name=_('Adjustment Time') )
	adjustment_note = models.CharField( max_length = 128, default = '', verbose_name=_('Adjustment Note') )
	
	@transaction.atomic
	def move_to( self, start_sequence_target ):
		if self.start_sequence == start_sequence_target:
			return
		while self.start_sequence != start_sequence_target:
			dir = -1 if self.start_sequence > start_sequence_target else 1
			try:
				e = EntryTT.objects.get(event=self.event, start_sequence=self.start_sequence+dir)
				self.start_sequence, e.start_sequence = e.start_sequence, self.start_sequence
				self.start_time, e.start_time = e.start_time, self.start_time
				e.save()
			except (EntryTT.DoesNotExist, EntryTT.MultipleObjectsReturned) as e:
				self.save()
				return False
		self.save()
		return True
	
	class Meta:
		unique_together = (
			('event', 'participant',),
		)
		index_together = (
			('event', 'start_sequence',),
		)

		verbose_name = _("Time Trial Entry")
		verbose_name_plural = _("Time Trial Entry")
		ordering = ['start_time']

class EventTT( Event ):
	def __init__( self, *args, **kwargs ):
		kwargs['event_type'] = 1
		super( EventTT, self ).__init__( *args, **kwargs )
		
	create_seeded_startlist = models.BooleanField( default=True, verbose_name=_('Create Seeded Startlist'),
		help_text=_('If True, seeded start times will be generated in the startlist for CrossMgr.  If False, no seeded times will be generated, and the TT time will start on the first recorded time in CrossMgr.') )

	@transaction.atomic
	def create_initial_seeding( self, respect_existing_hints=False ):
		if not self.create_seeded_startlist:
			EntryTT.objects.delete( event=self )
			return
		
		est_kmh = {}
		hint_sequence = {}
		for pk, kmh, hint in EntryTT.objects.filter(event=self).values_list('participant__pk', 'participant__est_kmh', 'hint_sequence'):
			est_kmh[pk] = kmh
			hint_sequence[pk] = hint
		
		sequenceCur = 1
		tCur = datetime.timedelta( seconds = 0 )
		for wave_tt in self.wavett_set.all():
			tCur += wave_tt.gap_before_wave
			participants = sorted(
				wave_tt.get_participants_unsorted(),
				key = lambda p: (
					hint_sequence.get(p.pk, 0) if respect_existing_hints else 0,
					est_kmh.get(p.pk, 0.0),
					p.license_holder.get_tt_metric(self.date_time.date())
				)
			)
			last_fastest = len(participants) - wave_tt.num_fastest_participants
			for i, p in enumerate(participants):
				if i != 0:
					tCur += wave_tt.fastest_participants_start_gap if i >= last_fastest else wave_tt.regular_start_gap
				entry_tt, created = EntryTT.objects.get_or_create(event=self, participant=p)
				entry_tt.start_time = tCur
				entry_tt.start_sequence = sequenceCur
				entry_tt.save()
				sequenceCur += 1
	
	def get_start_time( self, participant ):
		try:
			return EntryTT.objects.get(event=self, participant=participant).start_time
		except EntryTT.DoesNotExist as e:
			return None
			
	def get_participants_seeded( self ):
		participants = set()
		for w in self.get_wave_set().all():
			participants_cur = set( w.get_participants_unsorted().select_related('competition','license_holder','team') )
			for p in participants_cur:
				p.wave = w
			participants |= participants_cur

		participants = list( participants )
		
		if self.create_seeded_startlist:
			start_times = {
				pk: datetime.timedelta(seconds=start_time)
				for pk, start_time in EntryTT.objects.filter(
						participant__competition=self.competition,
						event=self,
					).values_list(
						'participant__pk',
						'start_time',
					)
			}
		else:
			start_times = {}
			
		for p in participants:
			p.start_time = start_times.get( p.pk, None )
			p.clock_time = None if p.start_time is None else self.date_time + p.start_time
		
		participants.sort( key=lambda p: (p.start_time.total_seconds() if p.start_time else 1000.0*24.0*60.0*60.0, p.bib or 0) )
		
		tDelta = datetime.timedelta( seconds = 0 )
		for i, p in enumerate(participants):
			if i > 0:
				try:
					tDeltaCur = p.start_time - participants[i-1].start_time
					if tDeltaCur != tDelta:
						if i > 1:
							p.gap_change = True
						tDelta = tDeltaCur
				except Exception as e:
					pass
		
		return participants
	
	def get_unseeded_count( self ):
		return sum( 1 for p in self.get_participants_seeded() if p.start_time is None ) if self.create_seeded_startlist else 0
		
	def has_unseeded( self ):
		if not self.create_seeded_startlist:
			return False
		participants = set( p.pk for p in self.get_participants() )
		start_times = set(
			EntryTT.objects.filter(
				participant__competition=self.competition,
				event=self,
			).values_list(
				'participant__pk',
				flat=True,
			)
		)
		participants_with_start_times = participants & start_times
		return len(participants_with_start_times) < len(participants)
		

	# Time Trial fields
	class Meta:
		verbose_name = _('Time Trial Event')
		verbose_name_plural = _('Time Trial Events')

#---------------------------------------------------------------------------------------------

class WaveTT( WaveBase ):
	event = models.ForeignKey( EventTT, db_index = True )
	
	sequence = models.PositiveSmallIntegerField( default=0, verbose_name = _('Sequence') )
	
	# Fields for assigning start times.	
	gap_before_wave = DurationField( verbose_name=_('Gap Before Wave'), default = 5*60 )
	regular_start_gap = DurationField( verbose_name=_('Regular Start Gap'), default = 1*60 )
	fastest_participants_start_gap = DurationField( verbose_name=_('Fastest Participants Start Gap'), default = 2*60 )
	num_fastest_participants = models.PositiveSmallIntegerField(
						verbose_name=_('Number of Fastest Participants'),
						choices=[(i, '%d' % i) for i in xrange(0, 16)],
						help_text = 'Participants to get the Fastest gap',
						default = 5)
	
	def save( self, *args, **kwargs ):
		init_sequence( WaveTT, self )
		return super( WaveTT, self ).save( *args, **kwargs )
	
	def get_speed( self, participant ):
		try:
			entry_tt = EntryTT.objects.get( event=self.event, participant=participant )
		except Exception as e:
			return None
		try:
			distance = self.distance
			return (distance / (entry_tt.finish_time - entry_tt.start_time).total_seconds()) * (60.0*60.0)
		except Exception as e:
			return None
	
	@property
	def gap_rules_html( self ):
		summary = [u'<table>']
		try:
			for label, value in (
					(_('GapBefore'), self.gap_before_wave),
					(_('RegGap'), self.regular_start_gap),
					(_('FastGap'), self.fastest_participants_start_gap),
					(_('NumFast'), self.num_fastest_participants),
				):
				summary.append( u'<tr><td class="text-right">{}&nbsp&nbsp</td><td class="text-right">{}</td><tr>'.format(label, unicode(value)) )
		except Exception as e:
			return e
		summary.append( '</table>' )
		return u''.join( summary )
	
	@property
	def gap_rules_text( self ):
		summary = []
		try:
			for label, value in (
					(_('GapBefore'), self.gap_before_wave),
					(_('RegGap'), self.regular_start_gap),
					(_('FastGap'), self.fastest_participants_start_gap),
					(_('NumFast'), self.num_fastest_participants),
				):
				summary.append( u'{}={}'.format(label, unicode(value)) )
		except Exception as e:
			return e
		return u' '.join( summary )
	
	def get_participants( self ):
		participants = list( self.get_participants_unsorted().select_related('competition','license_holder','team') )
		
		if not self.event.create_seeded_startlist:
			participants.sort( key=lambda p: p.bib or 0 )
			for p in participants:
				p.start_time = None
				p.clock_time = None				
			return participants
		
		start_times = {
			pk: datetime.timedelta(seconds=start_time)
			for pk, start_time in EntryTT.objects.filter(
					participant__competition=self.event.competition,
					event=self.event
				).values_list(
					'participant__pk',
					'start_time'
				)
		}
		for p in participants:
			p.start_time = start_times.get( p.pk, None )
			p.clock_time = None if p.start_time is None else self.event.date_time + p.start_time
		
		participants.sort( key=lambda p: (p.start_time if p.start_time else datetime.timedelta(days=100), p.bib or 0) )
		
		tDelta = datetime.timedelta(seconds = 0)
		for i in xrange(1, len(participants)):
			pPrev = participants[i-1]
			p = participants[i]
			try:
				tDeltaCur = p.start_time - pPrev.start_time
				if tDeltaCur != tDelta:
					if i > 1:
						p.gap_change = True
					tDelta = tDeltaCur
			except Exception as e:
				pass
		
		return participants
	
	def get_unseeded_participants( self ):
		if not self.event.create_seeded_startlist:
			return []
		
		has_start_time = set(
			EntryTT.objects.filter(
				participant__competition=self.event.competition,
				event=self.event
			).values_list(
				'participant__pk',
				flat=True
			)
		)
		return [p for p in self.get_participants_unsorted() if p.pk not in has_start_time]
	
	class Meta:
		verbose_name = _('TTWave')
		verbose_name_plural = _('TTWaves')
		ordering = ['sequence']

class ParticipantOption( models.Model ):
	competition = models.ForeignKey( Competition, db_index = True )
	participant = models.ForeignKey( Participant, db_index = True )
	option_id = models.PositiveIntegerField( verbose_name = ('Option Id') )
	
	@staticmethod
	@transaction.atomic
	def set_option_ids( participant, option_ids = [] ):
		ParticipantOption.objects.filter(competition=participant.competition, participant=participant).delete()
		for option_id in option_ids:
			ParticipantOption( competition=participant.competition, participant=participant, option_id=option_id ).save()
	
	@staticmethod
	def get_option_ids( competition, participant ):
		return ParticipantOption.objects.filter(competition=competition, participant=participant).values_list('option_id', flat=True)
	
	@staticmethod
	def delete_option_id( competition, option_id ):
		ParticipantOption.objects.filter(competition=competition, option_id=option_id).delete()
	
	@staticmethod
	@transaction.atomic
	def set_event_option_id( competition, event ):
		''' Get a unique option_id across MassStart and Time Trial events for this competition. '''
		ids = set()
		for EventClass in (EventMassStart, EventTT):
			ids |= set( EventClass.objects.filter(competition=competition)
							.exclude(option_id=0)
							.values_list('option_id', flat=True) )
		for id in xrange(1, 1000000):
			if id not in ids:
				break
		event.option_id = id
		event.save()

	class Meta:
		unique_together = (
			('competition', 'participant','option_id'),
		)
		index_together = (
			('competition', 'participant','option_id'),
			('competition', 'participant'),
			('competition', 'option_id'),
		)
		verbose_name = _("Participant Option")
		verbose_name_plural = _("Participant Options")

#-------------------------------------------------------------------------------------

# Apply upgrades.
# import migrate_data
