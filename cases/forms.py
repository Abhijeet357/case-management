from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Submit, Row, Column, Field
from .models import Case, Location, CaseType, Record, RecordRequisition, PPOMaster, UserProfile, get_workflow_for_case, get_current_stage_index, RetiringEmployee, timezone
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

    # ***** CORRECTED INDENTATION FOR __init__ METHOD *****
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

    # ***** CORRECTED INDENTATION FOR clean METHOD *****
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
class RecordRequisitionForm(forms.ModelForm):
    """
    A form for a Dealing Hand to request physical records for a specific case.
    """
    # This field will allow the user to select which records they need.
    records_requested = forms.ModelMultipleChoiceField(
        queryset=None, # The queryset is set dynamically in __init__
        widget=forms.CheckboxSelectMultiple,
        label="Select the records to be requisitioned",
        required=True
    )

    # This field allows the DH to select which AAO should approve the request.
    approving_aao = forms.ModelChoiceField(
        queryset=UserProfile.objects.filter(role='AAO', is_active_holder=True),
        label="Select Approving AAO",
        required=True
    )

    class Meta:
        model = RecordRequisition
        # We only need these two fields from the model for the creation form.
        # The other fields (case, requester_dh) will be set in the view.
        fields = ['records_requested', 'approving_aao']

    def __init__(self, *args, **kwargs):
        # The 'case' object is passed from the view to the form
        self.case = kwargs.pop('case', None)
        super().__init__(*args, **kwargs)

        if not self.case:
            # If for some reason the case is not passed, do not proceed.
            return

        # Dynamically set the queryset for the 'records_requested' field.
        # It should only show records that belong to the pensioner of the current case
        # and are currently 'AVAILABLE'.
        available_records = Record.objects.filter(
            pensioner=self.case.ppo_master,
            status='AVAILABLE'
        )
        self.fields['records_requested'].queryset = available_records

        # Add Crispy Forms helper for better layout
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'records_requested',
            'approving_aao',
            Submit('submit', 'Submit for Approval', css_class='btn btn-primary mt-3')
        )

    def clean(self):
        """
        Custom validation for the form.
        """
        cleaned_data = super().clean()
        records = cleaned_data.get('records_requested')

        # Ensure that the user has selected at least one record.
        if not records:
            raise forms.ValidationError(
                "You must select at least one record to requisition."
            )
        return cleaned_data
    
class RecordReturnForm(forms.ModelForm):
    """
    A form for a Dealing Hand to initiate the return of records they currently hold.
    """
    # This field will allow the user to select which of their held records to return.
    records_to_return = forms.ModelMultipleChoiceField(
        queryset=None, # Dynamically set in __init__
        widget=forms.CheckboxSelectMultiple,
        label="Select the records you are returning",
        required=True
    )

    # This field lets the DH select which AAO should approve the return.
    approving_aao = forms.ModelChoiceField(
        queryset=UserProfile.objects.filter(role='AAO', is_active_holder=True),
        label="Select Approving AAO for the return",
        required=True
    )

    class Meta:
        model = RecordRequisition
        # We rename 'records_requested' to 'records_to_return' for clarity in the form.
        # The model field remains the same, but the form field is what the user sees.
        fields = ['records_to_return', 'approving_aao']

    def __init__(self, *args, **kwargs):
        # The 'case' and 'user' objects are passed from the view
        self.case = kwargs.pop('case', None)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if not self.case or not self.user:
            return

        # Dynamically find the "User Desk" location for the current user.
        try:
            user_desk_location = Location.objects.get(custodian=self.user)

            # Set the queryset for the records field.
            # It should only show records that:
            # 1. Belong to the pensioner of the current case.
            # 2. Are currently located at the user's desk (meaning they hold them).
            # 3. Have a status of 'IN_USE'.
            records_held_by_user = Record.objects.filter(
                pensioner=self.case.ppo_master,
                current_location=user_desk_location,
                status='IN_USE'
            )
            self.fields['records_to_return'].queryset = records_held_by_user
        except Location.DoesNotExist:
            # If the user has never had a record handed to them, their desk location might not exist.
            # In this case, they have no records to return.
            self.fields['records_to_return'].queryset = Record.objects.none()


        # Add Crispy Forms helper for layout
        self.helper = FormHelper()
        self.helper.form_method = 'post'
        self.helper.layout = Layout(
            'records_to_return',
            'approving_aao',
            Submit('submit', 'Submit Return Request', css_class='btn btn-primary mt-3')
        )

    def save(self, commit=True):
        # Override the save method to correctly handle the renamed field.
        # The form uses 'records_to_return', but the model expects 'records_requested'.
        instance = super().save(commit=False)
        if commit:
            instance.save()
            # This is the crucial part: we assign the selected records from our
            # 'records_to_return' field to the instance's 'records_requested' ManyToMany field.
            instance.records_requested.set(self.cleaned_data['records_to_return'])
        return instance