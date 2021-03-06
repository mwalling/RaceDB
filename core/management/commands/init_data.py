from django.core.management.base import BaseCommand, CommandError
from core.models import *
import core.init_data

class Command(BaseCommand):
	args = ''
	help = 'Initialize the database with standard categories and disciplines'

	def handle(self, *args, **options):
		core.init_data.init_data( *args )
