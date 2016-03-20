from views_common import *
from django.utils.translation import ugettext_lazy as _

@autostrip
class DisciplineDisplayForm( Form ):
	def __init__( self, *args, **kwargs ):
		button_mask = kwargs.pop( 'button_mask', OK_BUTTON )
		
		super(DisciplineDisplayForm, self).__init__(*args, **kwargs)
		self.helper = FormHelper( self )
		self.helper.form_action = '.'
		self.helper.form_class = 'form-inline'
		
		btns = [('new-submit', _('New Discipline'), 'btn btn-success')]
		addFormButtons( self, button_mask, btns )

@autostrip
class DisciplineForm( ModelForm ):
	class Meta:
		model = Discipline
		fields = '__all__'
		
	def __init__( self, *args, **kwargs ):
		button_mask = kwargs.pop( 'button_mask', OK_BUTTON )
		
		super(DisciplineForm, self).__init__(*args, **kwargs)
		self.helper = FormHelper( self )
		self.helper.form_action = '.'
		self.helper.form_class = 'form-inline'
		
		self.helper.layout = Layout(
			Row(
				Col(Field('name', size=50), 4),
			),
			Field( 'sequence', type='hidden' ),
		)
		addFormButtons( self, button_mask )
		
@access_validation()
def DisciplinesDisplay( request ):
	NormalizeSequence( Discipline.objects.all() )
	if request.method == 'POST':
	
		if 'ok-submit' in request.POST:
			return HttpResponseRedirect(getContext(request,'cancelUrl'))
			
		if 'new-submit' in request.POST:
			return HttpResponseRedirect( pushUrl(request,'DisciplineNew') )
			
		form = DisciplineDisplayForm( request.POST )
	else:
		form = DisciplineDisplayForm()
		
	disciplines = Discipline.objects.all()
	return render_to_response( 'discipline_list.html', RequestContext(request, locals()) )

@access_validation()
def DisciplineNew( request ):
	return GenericNew( Discipline, request, DisciplineForm )

@access_validation()
def DisciplineEdit( request, disciplineId ):
	return GenericEdit( Discipline, request, disciplineId, DisciplineForm )
	
@access_validation()
def DisciplineDelete( request, disciplineId ):
	return GenericDelete( Discipline, request, disciplineId, DisciplineForm )

@access_validation()
def DisciplineDown( request, disciplineId ):
	discipline = get_object_or_404( Discipline, pk=disciplineId )
	SwapAdjacentSequence( Discipline, discipline, False )
	return HttpResponseRedirect(getContext(request,'cancelUrl'))
	
@access_validation()
def DisciplineUp( request, disciplineId ):
	discipline = get_object_or_404( Discipline, pk=disciplineId )
	SwapAdjacentSequence( Discipline, discipline, True )
	return HttpResponseRedirect(getContext(request,'cancelUrl'))

@access_validation()
def DisciplineBottom( request, disciplineId ):
	discipline = get_object_or_404( Discipline, pk=disciplineId )
	NormalizeSequence( Discipline.objects.all() )
	MoveSequence( Discipline, discipline, False )
	return HttpResponseRedirect(getContext(request,'cancelUrl'))

@access_validation()
def DisciplineTop( request, disciplineId ):
	discipline = get_object_or_404( Discipline, pk=disciplineId )
	NormalizeSequence( Discipline.objects.all() )
	MoveSequence( Discipline, discipline, True )
	return HttpResponseRedirect(getContext(request,'cancelUrl'))
	