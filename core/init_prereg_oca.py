import sys
import datetime
from xlrd import open_workbook, xldate_as_tuple
from six.moves.html_parser import HTMLParser
from collections import namedtuple
from django.db import transaction, IntegrityError
from django.db.models import Q

from .models import *
from .import_utils import *
from .large_delete_all import large_delete_all

datemode = None

today = datetime.date.today()
earliest_year = (today - datetime.timedelta( days=106*365 )).year
latest_year = (today - datetime.timedelta( days=7*365 )).year

def date_from_value( s ):
	if isinstance(s, datetime.date):
		return s
	if isinstance(s, (float, int)):
		return datetime.date( *(xldate_as_tuple(s, datemode)[:3]) )
	
	# Assume month, day, year format.
	mm, dd, yy = [int(v.strip()) for v in s.split( '/' )]
	
	# Correct for 2-digit year.
	for century in [0, 1900, 2000, 2100]:
		if earliest_year <= yy + century <= latest_year:
			yy += century
			break
	
	# Check if day and month are reversed.
	if mm > 12:
		dd, mm = mm, dd
		
	assert 1900 <= yy
		
	try:
		return datetime.date( year = yy, month = mm, day = dd )
	except Exception as e:
		safe_print( yy, mm, dd )
		raise e
		
def gender_from_str( s ):
	return 0 if s.lower().strip().startswith('m') else 1

def set_attributes( obj, attributes ):
	changed = False
	for key, value in attributes.items():
		if getattr(obj, key) != value:
			setattr(obj, key, value)
			changed = True
	return changed
	
def to_int_str( v ):
	try:
		return unicode(long(v))
	except:
		pass
	return u'{}'.format(v)
		
def to_str( v ):
	if v is None:
		return v
	return u'{}'.format(v)
	
def to_bool( v ):
	if v is None:
		return None
	s = u'{}'.format(v)
	return s[:1] in 'YyTt1'

def to_int( v ):
	if v is None:
		return None
	try:
		return int(v)
	except:
		return None
		
def to_tag( v ):
	if v is None:
		return None
	return u'{}'.format(v).split('.')[0]

def init_prereg_oca( competition_name, worksheet_name, clear_existing ):
	global datemode
	
	tstart = datetime.datetime.now()
	
	html_parser = HTMLParser()

	try:
		competition = Competition.objects.get( name=competition_name )
	except Competition.DoesNotExist:
		safe_print( u'Cannot find Competition: "{}"'.format(competition_name) )
		return
	except Competition.MultipleObjectsReturned:
		safe_print( u'Found multiple Competitions matching: "{}"'.format(competition_name) )
		return
	
	if clear_existing:
		Participant.objects.filter(competition=competition).delete()
	
	# Process the records in large transactions for efficiency.
	@transaction.atomic
	def process_ur_records( ur_records ):
		
		for i, ur in ur_records:
			bib				= to_int(ur.get('bibnum', None))
			license_code	= 'ON' + (to_int_str(ur.get('license','')) or to_int_str(ur.get('licence','<missing license code>')))
			name			= to_str(ur.get('name','')).strip()
			team_name		= to_str(ur.get('Team', None))
			preregistered	= to_bool(ur.get('preregistered', True))
			paid			= to_bool(ur.get('paid', None))
			category_code   = to_str(ur.get('category', None))

			emergency_contact_name = to_str(get_key(ur,('Emergency Contact','Emergency Contact Name'), None))
			emergency_contact_phone = to_str(get_key(ur,('Emergency Phone','Emergency Contact Phone'), None))
			
			try:
				license_holder = LicenseHolder.objects.get( license_code=license_code )
			except LicenseHolder.DoesNotExist:
				safe_print( u'Row {}: cannot find LicenceHolder from LicenseCode: {}'.format(i, license_code) )
				continue
			
			do_save = False
			for fname, fvalue in (  ('emergency_contact_name',emergency_contact_name),
									('emergency_contact_phone',emergency_contact_name) ):
				if fvalue and getattr(license_holder, fname) != fvalue:
					setattr( license_holder, fname, fvalue )
					do_save = True
			if do_save:
				license_holder.save()
					
			try:
				participant = Participant.objects.get( competition=competition, license_holder=license_holder )
			except Participant.DoesNotExist:
				participant = Participant( competition=competition, license_holder=license_holder )
			except Participant.MultipleObjectsReturned:
				safe_print( u'Row {}: found multiple Participants for this competition and license_holder.'.format(
						i,
				) )
				continue
			
			for attr, value in [ ('preregistered',preregistered), ('paid',paid), ('bib',bib), ]:
				if value is not None:
					setattr( participant, attr, value )
			
			team = None
			if team_name is not None:
				try:
					team = Team.objects.get(name=team_name)
				except Team.DoesNotExist:
					safe_print( u'Row {}: unrecognized Team name (ignoring): "{}"'.format(
						i, team_name,
					) )
				except Team.MultipleObjectsReturned:
					safe_print( u'Row {}: multiple Teams match name (ignoring): "{}"'.format(
						i, team_name,
					) )
			participant.team = team
			
			category = None
			if category_code is not None:
				try:
					category = Category.objects.get( format=competition.category_format, code=category_code )
				except Category.DoesNotExist:
					safe_print( u'Row {}: unrecognized Category code (ignoring): "{}"'.format(
						i, category_code,
					) )
				except Category.MultipleObjectsReturned:
					safe_print( u'Row {}: multiple Categories match code (ignoring): "{}"'.format(
						i, category_code,
					) )
			participant.category = category
			
			try:
				participant.save()
			except IntegrityError as e:
				safe_print( u'Row {}: Error={}\nBib={} Category={} License={} Name={}'.format(
					i, e,
					bib, category_code, license_code, name,
				) )
				continue
			
			participant.add_to_default_optional_events()
			
			safe_print( u'{:>6}: {:>8} {:>10} {}, {}, {}, {}, {}'.format(
					i,
					license_holder.license_code, license_holder.date_of_birth.strftime('%Y/%m/%d'),
					license_holder.uci_code,
					license_holder.last_name, license_holder.first_name,
					license_holder.city, license_holder.state_prov
				)
			)
	
	try:
		fname, sheet_name = worksheet_name.split('$')
	except:
		fname = worksheet_name
		sheet_name = None
		
	ur_records = []
	wb = open_workbook( fname )
	datemode = wb.datemode
	
	ws = None
	for cur_sheet_name in wb.sheet_names():
		if cur_sheet_name == sheet_name or sheet_name is None:
			safe_print( u'Reading sheet: {}'.format(cur_sheet_name) )
			ws = wb.sheet_by_name(cur_sheet_name)
			break
	
	if not ws:
		safe_print( u'Cannot find sheet "{}"'.format(sheet_name) )
		return
		
	num_rows = ws.nrows
	num_cols = ws.ncols
	for r in six.moves.range(num_rows):
		row = ws.row( r )
		if r == 0:
			# Get the header fields from the first row.
			fields = [html_parser.unescape(u'{}'.format(v.value).strip()).replace('-','_').replace('#','').strip().replace('4', 'four').replace(' ','_').lower() for v in row]
			fields = ['f{}'.format(i) if not f else f.strip() for i, f in enumerate(fields)]
			safe_print( u'\n'.join( fields ) )
			continue
			
		ur = dict( (f, row[c].value) for c, f in enumerate(fields) )
		ur_records.append( (r+1, ur) )
		if len(ur_records) == 1000:
			process_ur_records( ur_records )
			ur_records = []
			
	process_ur_records( ur_records )
	
	safe_print( u'Initialization in: ', datetime.datetime.now() - tstart )
