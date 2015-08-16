
import datetime
import utils
from collections import defaultdict
from models import *

def participation_data( year=None, discipline=None, race_class=None ):
	competitions = Competition.objects.all()
	if year is not None:
		competitions = competitions.filter( start_date__year = year )
	if discipline is not None:
		competitions = competitions.filter( discipline = discipline )
	if race_class is not None:
		competitions = competitions.filter( race_class = race_class )
	
	data = []
	license_holders_count = defaultdict( int )
	license_holders_men_count = defaultdict( int )
	license_holders_women_count = defaultdict( int )
	age_count = defaultdict( int )
	age_men_count = defaultdict( int )
	age_women_count = defaultdict( int )
	
	age_increment = 5
	age_range_license_holders = [set() for i in xrange(0, 120, age_increment)]
	age_range_participant_count = [0 for i in xrange(0, 120, age_increment)]
	age_range_men_license_holders = [set() for i in xrange(0, 120, age_increment)]
	age_range_men_participant_count = [0 for i in xrange(0, 120, age_increment)]
	age_range_women_license_holders = [set() for i in xrange(0, 120, age_increment)]
	age_range_women_participant_count = [0 for i in xrange(0, 120, age_increment)]
	license_holders_set = set()
	
	profile_year = 0
	for competition in competitions.order_by( 'start_date' ):
		if not competition.has_participants():
			continue
		
		profile_year = max( profile_year, competition.start_date.year )
		
		competition_data = {
			'name': competition.name,
			'start_date': competition.start_date.strftime('%Y-%m-%d'),
			'events': [],
			'men': 0,
			'women': 0,
			'total': 0,
		}
		for event in competition.get_events():
			if not event.has_participants():
				continue
			participant_data = []
			for participant in event.get_participants():
				age = event.date_time.year - participant.license_holder.date_of_birth.year
				participant_data.append( {
					'gender':	participant.license_holder.gender,
					'age':		age,
				} )
				license_holders_set.add( participant.license_holder )
				license_holders_count[participant.license_holder] += 1
				age_count[age] += 1
				
				age_range_license_holders[age//5].add( participant.license_holder )
				age_range_participant_count[age//5] += 1
				
				if participant.license_holder.gender == 0:
					license_holders_men_count[participant.license_holder] += 1
					age_men_count[age] += 1
					age_range_men_license_holders[age//5].add( participant.license_holder )
					age_range_men_participant_count[age//5] += 1
				else:
					license_holders_women_count[participant.license_holder] += 1
					age_women_count[age] += 1
					age_range_women_license_holders[age//5].add( participant.license_holder )
					age_range_women_participant_count[age//5] += 1
			
			event_data = {
				'name':event.name,
				'participants':participant_data,
				'men': sum(1 for p in participant_data if p['gender'] == 0),
				'women': sum(1 for p in participant_data if p['gender'] == 1),
			}
			event_data['total'] = event_data['men'] + event_data['women']
			competition_data['men'] += event_data['men']
			competition_data['women'] += event_data['women']
			competition_data['events'].append( event_data )
		
		competition_data['total'] = competition_data['men'] + competition_data['women']
		data.append( competition_data )
	
	age_range_average = [
		0 if not age_range_license_holders[i] else age_range_participant_count[i] / float(len(age_range_license_holders[i]))
		for i in xrange(len(age_range_participant_count))
	]
	age_range_men_average = [
		0 if not age_range_men_license_holders[i] else age_range_men_participant_count[i] / float(len(age_range_men_license_holders[i]))
		for i in xrange(len(age_range_men_participant_count))
	]
	age_range_women_average = [
		0 if not age_range_women_license_holders[i] else age_range_women_participant_count[i] / float(len(age_range_women_license_holders[i]))
		for i in xrange(len(age_range_women_participant_count))
	]
	
	def trim_right_zeros( a ):
		for i in xrange(len(a)-1, -1, -1):
			if a[i]:
				del a[i+1:]
				break
	
	trim_right_zeros( age_range_average )
	trim_right_zeros( age_range_men_average )
	trim_right_zeros( age_range_women_average )
	
	license_holder_profile = []
	license_holder_men_profile = []
	license_holder_women_profile = []
	if profile_year:
		license_holder_profile = sorted(profile_year - lh.date_of_birth.year for lh in license_holders_set)
		license_holder_men_profile = sorted(profile_year - lh.date_of_birth.year for lh in license_holders_set if lh.gender == 0)
		license_holder_women_profile = sorted(profile_year - lh.date_of_birth.year for lh in license_holders_set if lh.gender == 1)
	else:
		profile_year = datetime.date.today().year
	
	def get_expected_age( ac ):
		if not ac:
			return None
		most_frequent = max( v for v in ac.itervalues() )
		for a, c in ac.iteritems():
			if c == most_frequent:
				return a
		return None
	
	payload = {
		'participants_total': sum(c['total'] for c in data),
		'participants_men_total': sum(c['men'] for c in data),
		'participants_women_total': sum(c['women'] for c in data),
		
		'license_holders_total': len(license_holders_count),
		'license_holders_men_total': len(license_holders_men_count),
		'license_holders_women_total': len(license_holders_women_count),
		
		'events_average': sum(v for v in license_holders_count.itervalues()) / (float(len(license_holders_count)) or 1),
		'events_men_average': sum(v for v in license_holders_men_count.itervalues()) / (float(len(license_holders_men_count)) or 1),
		'events_women_average': sum(v for v in license_holders_women_count.itervalues()) / (float(len(license_holders_women_count)) or 1),
		
		'expected_age': get_expected_age(age_count),
		'expected_men_age': get_expected_age(age_men_count),
		'expected_women_age': get_expected_age(age_women_count),
		
		'age_range_average':age_range_average,
		'age_range_men_average':age_range_men_average,
		'age_range_women_average':age_range_women_average,
		'age_increment': age_increment,
		
		'profile_year':profile_year,
		'license_holder_profile':license_holder_profile,
		'license_holder_men_profile':license_holder_men_profile,
		'license_holder_women_profile':license_holder_women_profile,
		
		'competitions': data,
	}
	return payload