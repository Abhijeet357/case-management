# Full corrected cases/forms.py with RetiringEmployee import added

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Field
from .models import Case, CaseType, PPOMaster, UserProfile, get_workflow_for_case, get_current_stage_index, RetiringEmployee  # Added RetiringEmployee

class CaseRegistrationForm(forms.ModelForm):
    ppo_number = forms.CharField(max_length=20, required=False, label="PPO Number")
    name_pensioner = forms.CharField(max_length=200, required=False, label="Name of the pensioner", widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    mobile_number = forms.CharField(max_length=15, required=False, label="Mobile Number", widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    last_lc_done_date = forms.DateField(required=False, label="Last LC Done date", widget=forms.DateInput(attrs={'readonly': 'readonly'}))
    kyp_flag = forms.BooleanField(required=False, label="KYP Flag", widget=forms.CheckboxInput(attrs={'disabled': 'disabled'}))
    mode_of_receipt = forms.ChoiceField(choices=Case.MODE_OF_RECEIPT_CHOICES, required=False, label="Mode of Receipt")
    date_of_death = forms.DateField(required=False, label="Date of death", widget=forms.DateInput(attrs={'type': 'date'}))
    name_claimant = forms.CharField(max_length=200, required=False, label="Name of the Claimant")
    relationship = forms.CharField(max_length=50, required=False, label="Relationship with the deceased")
    service_book_enclosed = forms.BooleanField(required=False, label="Whether Service book also enclosed")
    type_of_correction = forms.ChoiceField(choices=Case.TYPE_OF_CORRECTION_CHOICES, required=False, label="Type of Correction / modification")
    original_ppo_submitted = forms.BooleanField(required=False, label="Whether Original PPO Submitted along with application?")
    fresh_or_compliance = forms.ChoiceField(choices=Case.FRESH_COMPLIANCE_CHOICES, required=False, label="Whether Fresh Case or Compliance")
    type_of_employee = forms.ChoiceField(choices=Case.TYPE_OF_EMPLOYEE_CHOICES, required=False, label="Type of Employee")
    retiring_employee = forms.ModelChoiceField(queryset=RetiringEmployee.objects.none(), required=False, label="Name of the employee")
    
    class Meta:
        model = Case
        fields = ['case_type', 'sub_category', 'case_description', 'applicant_name', 'priority', 'ppo_number', 'name_pensioner', 'mobile_number', 'last_lc_done_date', 'kyp_flag', 'mode_of_receipt', 'date_of_death', 'name_claimant', 'relationship', 'service_book_enclosed', 'type_of_correction', 'original_ppo_submitted', 'fresh_or_compliance', 'type_of_employee', 'retiring_employee']
        widgets = {
            'case_description': forms.Textarea(attrs={'rows': 3}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('case_type', css_class='form-group col-md-6 mb-0'),
                Column('sub_category', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('applicant_name', css_class='form-group col-md-6 mb-0'),
                Column('ppo_number', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('priority', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            # Conditional fields - grouped in divs in template
            'name_pensioner',
            'mobile_number',
            'last_lc_done_date',
            'kyp_flag',
            'mode_of_receipt',
            'date_of_death',
            'name_claimant',
            'relationship',
            'service_book_enclosed',
            'type_of_correction',
            'original_ppo_submitted',
            'fresh_or_compliance',
            'type_of_employee',
            'retiring_employee',
            'case_description',
            Submit('submit', 'Register Case', css_class='btn btn-primary')
        )
        
        # Initialize sub_category choices
        self.fields['sub_category'].choices = [('', 'Select Sub-Category')]
        
        # Make sub_category dependent on case_type
        if 'case_type' in self.data:
            try:
                case_type_id = int(self.data.get('case_type'))
                case_type = CaseType.objects.get(id=case_type_id)
                sub_cats = case_type.get_sub_categories_list()
                self.fields['sub_category'].choices = [(cat, cat) for cat in sub_cats]
            except (ValueError, TypeError, CaseType.DoesNotExist):
                pass
        elif self.instance.pk:
            if self.instance.case_type:
                sub_cats = self.instance.case_type.get_sub_categories_list()
                self.fields['sub_category'].choices = [(cat, cat) for cat in sub_cats]

class CaseMovementForm(forms.Form):
    MOVEMENT_CHOICES = [
        ('forward', 'Move Forward'),
        ('backward', 'Move Backward'),
        ('reassign', 'Re-assign'),
        ('complete', 'Complete Case'),
    ]
    
    movement_type = forms.ChoiceField(choices=MOVEMENT_CHOICES)
    to_holder = forms.ModelChoiceField(queryset=UserProfile.objects.none(), required=False, label="Select Holder")
    comments = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}))
    
    def __init__(self, *args, **kwargs):
        case = kwargs.pop('case', None)
        movement_type = kwargs.get('initial', {}).get('movement_type')  # For pre-pop
        super().__init__(*args, **kwargs)
        
        self.helper = FormHelper()
        self.helper.layout = Layout(
            'movement_type',
            'to_holder',
            'comments',
            Submit('submit', 'Move Case', css_class='btn btn-primary')
        )
        
        if case:
            workflow = get_workflow_for_case(case)
            current_index = get_current_stage_index(case, workflow)
            queryset = UserProfile.objects.none()
            
            if movement_type == 'reassign':
                queryset = UserProfile.objects.filter(
                    role=case.current_holder.role, 
                    is_active_holder=True
                ).exclude(id=case.current_holder.id)
            elif movement_type == 'forward':
                if current_index < len(workflow) - 1:
                    next_stage = workflow[current_index + 1]
                    queryset = UserProfile.objects.filter(role=next_stage, is_active_holder=True)
            elif movement_type == 'backward':
                if current_index > 0:
                    prev_stage = workflow[current_index - 1]
                    queryset = UserProfile.objects.filter(role=prev_stage, is_active_holder=True)
            
            self.fields['to_holder'].queryset = queryset
            if movement_type != 'complete' and queryset.exists():
                self.fields['to_holder'].required = True
            else:
                self.fields['to_holder'].required = False

    def clean(self):
        cleaned_data = super().clean()
        movement_type = cleaned_data.get('movement_type')
        to_holder = cleaned_data.get('to_holder')
        
        if movement_type in ['forward', 'backward', 'reassign'] and self.fields['to_holder'].required and not to_holder:
            self.add_error('to_holder', "Please select a holder.")
        
        return cleaned_data

class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)
    first_name = forms.CharField(max_length=30, required=True)
    last_name = forms.CharField(max_length=30, required=True)
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES)
    phone = forms.CharField(max_length=15, required=False)
    department = forms.CharField(max_length=100, required=False)
    
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'password1', 'password2')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Row(
                Column('first_name', css_class='form-group col-md-6 mb-0'),
                Column('last_name', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('username', css_class='form-group col-md-6 mb-0'),
                Column('email', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Row(
                Column('role', css_class='form-group col-md-6 mb-0'),
                Column('department', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            'phone',
            Row(
                Column('password1', css_class='form-group col-md-6 mb-0'),
                Column('password2', css_class='form-group col-md-6 mb-0'),
                css_class='form-row'
            ),
            Submit('submit', 'Register User', css_class='btn btn-primary')
        )
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        
        if commit:
            user.save()
            UserProfile.objects.create(
                user=user,
                role=self.cleaned_data['role'],
                phone=self.cleaned_data.get('phone', ''),
                department=self.cleaned_data.get('department', '')
            )
        return user

class PPOSearchForm(forms.Form):
    ppo_number = forms.CharField(max_length=20)
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_method = 'get'
        self.helper.layout = Layout(
            Row(
                Column('ppo_number', css_class='form-group col-md-8 mb-0'),
                Column(Submit('search', 'Search PPO', css_class='btn btn-primary'), css_class='form-group col-md-4 mb-0'),
                css_class='form-row'
            )
        )

class BulkImportForm(forms.Form):
    csv_file = forms.FileField(help_text="Upload CSV file with case data")
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            'csv_file',
            Submit('submit', 'Import Cases', css_class='btn btn-warning')
        )