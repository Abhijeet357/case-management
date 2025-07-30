from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Field
from .models import Case, CaseType, PPOMaster, UserProfile, get_workflow_for_case, get_current_stage_index, RetiringEmployee, timezone
from dateutil.relativedelta import relativedelta
from datetime import date, timedelta

class CaseRegistrationForm(forms.ModelForm):
    ppo_number = forms.CharField(max_length=20, required=False, label="PPO Number")
    name_pensioner = forms.CharField(max_length=200, required=False, label="Name of the pensioner", widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    registered_mobile = forms.CharField(max_length=15, required=False, label="Registered Mobile Number", widget=forms.TextInput(attrs={'readonly': 'readonly'}))
    manual_mobile = forms.CharField(max_length=15, required=False, label="Mobile Number")
    last_lc_done_date = forms.DateField(required=False, label="Last LC Done date", widget=forms.TextInput(attrs={'placeholder': 'dd-mm-yyyy'}))
    kyp_flag = forms.BooleanField(required=False, label="KYP Flag", widget=forms.CheckboxInput(attrs={'disabled': 'disabled'}))
    mode_of_receipt = forms.ChoiceField(choices=Case.MODE_OF_RECEIPT_CHOICES, required=False, label="Mode of Receipt")
    date_of_death = forms.DateField(required=False, label="Date of death", widget=forms.TextInput(attrs={'placeholder': 'dd-mm-yyyy'}))
    name_claimant = forms.CharField(max_length=200, required=False, label="Name of the Claimant")
    relationship = forms.CharField(max_length=50, required=False, label="Relationship with the deceased")
    service_book_enclosed = forms.BooleanField(required=False, label="Whether Service book also enclosed")
    type_of_correction = forms.ChoiceField(choices=Case.TYPE_OF_CORRECTION_CHOICES, required=False, label="Type of Correction / modification")
    original_ppo_submitted = forms.BooleanField(required=False, label="Whether Original PPO Submitted along with application?")
    fresh_or_compliance = forms.ChoiceField(choices=Case.FRESH_COMPLIANCE_CHOICES, required=False, label="Whether Fresh Case or Compliance")
    type_of_employee = forms.ChoiceField(choices=Case.TYPE_OF_EMPLOYEE_CHOICES, required=False, label="Type of Employee")
    retiring_employee = forms.ModelChoiceField(queryset=RetiringEmployee.objects.none(), required=False, label="Name of the employee")
    type_of_pension = forms.ChoiceField(choices=Case.TYPE_OF_PENSION_CHOICES, required=False, label="Type of Pension")
    type_of_pensioner = forms.ChoiceField(choices=Case.TYPE_OF_PENSIONER_CHOICES, required=False, label="Type of Pensioner")
    date_of_retirement = forms.DateField(required=False, label="Date of Retirement", widget=forms.TextInput(attrs={'readonly': 'readonly', 'placeholder': 'dd-mm-yyyy'}))
    initial_holder = forms.ModelChoiceField(queryset=UserProfile.objects.filter(role='DH', is_active_holder=True), required=True, label="Assigned to Dealing Hand")

    # New fields for Superannuation
    retirement_month = forms.ChoiceField(choices=[(i, f'{i:02d}') for i in range(1, 13)], required=False, label="Month of Retirement")
    retirement_year = forms.ChoiceField(choices=[], required=False, label="Year of Retirement")

    class Meta:
        model = Case
        fields = ['case_type', 'priority', 'ppo_number', 'name_pensioner', 'registered_mobile', 'manual_mobile', 'last_lc_done_date', 'kyp_flag', 'mode_of_receipt', 'date_of_death', 'name_claimant', 'relationship', 'service_book_enclosed', 'type_of_correction', 'original_ppo_submitted', 'fresh_or_compliance', 'type_of_employee', 'retiring_employee', 'type_of_pension', 'type_of_pensioner', 'date_of_retirement', 'initial_holder', 'retirement_month', 'retirement_year']

def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.helper = FormHelper()
    self.helper.layout = None  # Remove layout to render manually in template for conditionals

    # Dynamic year choices: current year to current + 2
    current_year = date.today().year
    self.fields['retirement_year'].choices = [(y, str(y)) for y in range(current_year, current_year + 3)]

    # Set retiring_employee queryset dynamically - FIXED VERSION
    if self.data and self.data.get('retirement_month') and self.data.get('retirement_year'):
        try:
            month = int(self.data['retirement_month'])
            year = int(self.data['retirement_year'])
            from_date = date(year, month, 1)
            to_date = (from_date + relativedelta(months=1)) - timedelta(days=1)
            self.fields['retiring_employee'].queryset = RetiringEmployee.objects.filter(
                retirement_date__gte=from_date,
                retirement_date__lte=to_date
            )
        except (ValueError, TypeError):
            self.fields['retiring_employee'].queryset = RetiringEmployee.objects.none()
    elif self.initial.get('retirement_month') and self.initial.get('retirement_year'):
        try:
            month = int(self.initial['retirement_month'])
            year = int(self.initial['retirement_year'])
            from_date = date(year, month, 1)
            to_date = (from_date + relativedelta(months=1)) - timedelta(days=1)
            self.fields['retiring_employee'].queryset = RetiringEmployee.objects.filter(
                retirement_date__gte=from_date,
                retirement_date__lte=to_date
            )
        except (ValueError, TypeError):
            self.fields['retiring_employee'].queryset = RetiringEmployee.objects.none()
    else:
        self.fields['retiring_employee'].queryset = RetiringEmployee.objects.none()

    def clean(self):
        cleaned_data = super().clean()
        case_type = cleaned_data.get('case_type')
        if case_type:
            type_name = case_type.name
            required_fields = []
            if type_name == 'Know Your Pensioner (KYP)':
                required_fields = ['ppo_number', 'name_pensioner', 'manual_mobile', 'mode_of_receipt']
            elif type_name == 'Family Pension - Death in Service':
                required_fields = ['ppo_number', 'name_pensioner', 'date_of_death', 'name_claimant', 'relationship', 'manual_mobile', 'service_book_enclosed']
            elif type_name == 'Family Pension - Extended Family Pension':
                required_fields = ['ppo_number', 'name_pensioner', 'date_of_death', 'name_claimant', 'relationship', 'manual_mobile']
            elif type_name == 'Life Time Arrears (LTA)':
                required_fields = ['ppo_number', 'name_pensioner', 'date_of_death', 'name_claimant', 'relationship', 'manual_mobile']
            elif type_name == 'PPO Correction':
                required_fields = ['type_of_correction', 'ppo_number', 'name_pensioner', 'original_ppo_submitted']
            elif type_name == 'Superannuation':
                required_fields = ['fresh_or_compliance', 'type_of_employee', 'retiring_employee', 'service_book_enclosed', 'retirement_month', 'retirement_year']
            elif type_name == 'Fixed Medical Allowance (FMA)':
                required_fields = ['ppo_number', 'name_pensioner', 'manual_mobile']
            elif type_name == 'Death Intimation':
                required_fields = ['ppo_number', 'name_pensioner', 'type_of_pension', 'type_of_pensioner', 'date_of_death', 'name_claimant', 'relationship', 'manual_mobile', 'service_book_enclosed']
            elif type_name == 'Family Pension - Conversion of Superannuation':
                required_fields = ['ppo_number', 'name_pensioner', 'type_of_pension', 'date_of_death', 'name_claimant', 'relationship', 'manual_mobile', 'service_book_enclosed']

            for field in required_fields:
                if not cleaned_data.get(field):
                    self.add_error(field, f'This field is required for {type_name}.')
        return cleaned_data

class CaseMovementForm(forms.Form):
    MOVEMENT_CHOICES = [
        ('forward', 'Move Forward'),
        ('backward', 'Move Backward'),
        ('reassign', 'Re-assign'),
        ('complete', 'Complete Case'),
    ]

    movement_type = forms.ChoiceField(
        choices=MOVEMENT_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_movement_type'})
    )
    to_holder = forms.ModelChoiceField(
        queryset=UserProfile.objects.none(), 
        required=False, 
        label="Select Holder",
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_to_holder'}),
        empty_label="-- Select a holder --"
    )
    comments = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'Add comments about this movement...'}),
        required=True,
        label="Comments"
    )

    def __init__(self, *args, **kwargs):
        case = kwargs.pop('case', None)
        super().__init__(*args, **kwargs)

        self.case = case
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            Field('movement_type', css_class='form-group'),
            Field('to_holder', css_class='form-group'),
            Field('comments', css_class='form-group'),
            Submit('submit', 'Move Case', css_class='btn btn-primary')
        )

        # Set initial queryset based on movement type
        if case:
            movement_type = self.data.get('movement_type') or self.initial.get('movement_type')
            self.update_holder_queryset(movement_type)

    def update_holder_queryset(self, movement_type):
        """Update the to_holder queryset based on movement type and case"""
        if not self.case:
            self.fields['to_holder'].queryset = UserProfile.objects.none()
            return

        workflow = get_workflow_for_case(self.case)
        current_index = get_current_stage_index(self.case, workflow)
        queryset = UserProfile.objects.none()

        try:
            if movement_type == 'reassign':
                # Same stage, different person
                queryset = UserProfile.objects.filter(
                    role=self.case.current_holder.role, 
                    is_active_holder=True
                ).exclude(id=self.case.current_holder.id)

            elif movement_type == 'forward':
                # Next stage in workflow
                if current_index < len(workflow) - 1:
                    next_stage = workflow[current_index + 1]
                    queryset = UserProfile.objects.filter(
                        role=next_stage, 
                        is_active_holder=True
                    )

            elif movement_type == 'backward':
                # Previous stage in workflow
                if current_index > 0:
                    prev_stage = workflow[current_index - 1]
                    queryset = UserProfile.objects.filter(
                        role=prev_stage, 
                        is_active_holder=True
                    )

            elif movement_type == 'complete':
                # No holder selection needed for completion
                queryset = UserProfile.objects.none()

        except (ValueError, IndexError) as e:
            print(f"Error updating holder queryset: {e}")
            queryset = UserProfile.objects.none()

        self.fields['to_holder'].queryset = queryset

        # Set field as required only if we need to select a holder
        self.fields['to_holder'].required = (
            movement_type in ['forward', 'backward', 'reassign'] and 
            queryset.exists()
        )

    def clean(self):
        cleaned_data = super().clean()
        movement_type = cleaned_data.get('movement_type')
        to_holder = cleaned_data.get('to_holder')

        if not self.case:
            raise forms.ValidationError("Case information is missing.")

        # Validate movement type specific requirements
        if movement_type in ['forward', 'backward', 'reassign']:
            if self.fields['to_holder'].required and not to_holder:
                self.add_error('to_holder', "Please select a holder for this movement.")

            # Additional validation for workflow constraints
            workflow = get_workflow_for_case(self.case)
            current_index = get_current_stage_index(self.case, workflow)

            if movement_type == 'forward' and current_index >= len(workflow) - 1:
                raise forms.ValidationError("Cannot move forward - case is already at the final stage.")

            if movement_type == 'backward' and current_index <= 0:
                raise forms.ValidationError("Cannot move backward - case is already at the first stage.")

            if movement_type == 'reassign' and to_holder and to_holder.role != self.case.current_holder.role:
                self.add_error('to_holder', "For reassignment, the new holder must be in the same role.")

        elif movement_type == 'complete':
            # Validate completion rules
            workflow = get_workflow_for_case(self.case)
            current_index = get_current_stage_index(self.case, workflow)

            if current_index < 1:  # DH is index 0
                raise forms.ValidationError("Cases can only be completed from AAO level onwards.")

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
