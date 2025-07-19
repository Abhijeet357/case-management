# cases/views.py (added imports for date, timedelta, relativedelta)

# cases/views.py (ensured imports are at top)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, Count
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
import json
import csv
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from .models import Case, CaseType, PPOMaster, UserProfile, CaseMovement, WORKFLOW_STAGES, get_workflow_for_case, get_current_stage_index, get_status_color, FamilyPensionClaim, RetiringEmployee
from .forms import CaseRegistrationForm, CaseMovementForm, UserRegistrationForm, PPOSearchForm, BulkImportForm

# ... (rest of the views code remains the same)
@login_required
def dashboard(request):
    """Main dashboard view"""
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    # Get cases for current user
    my_cases = Case.objects.filter(current_holder=user_profile, is_completed=False)
    
    # Get summary statistics
    total_cases = Case.objects.count()
    pending_cases = Case.objects.filter(is_completed=False).count()
    completed_cases = Case.objects.filter(is_completed=True).count()
    overdue_cases = Case.objects.filter(
        is_completed=False,
        expected_completion__lt=timezone.now()
    ).count()
    
    # Get cases by priority
    high_priority = Case.objects.filter(priority='High', is_completed=False).count()
    medium_priority = Case.objects.filter(priority='Medium', is_completed=False).count()
    low_priority = Case.objects.filter(priority='Low', is_completed=False).count()
    
    # Get recent cases
    recent_cases = Case.objects.all()[:10]
    
    # Get cases by stage (for admin users)
    stage_stats = {}
    if user_profile.role == 'ADMIN':
        for stage in ['DH', 'AAO', 'AO', 'Jt.CCA', 'CCA', 'Pr.CCA']:
            stage_stats[stage] = Case.objects.filter(
                current_holder__role=stage,
                is_completed=False
            ).count()
    
    # Add unclaimed Death Intimation for monitoring (fixed typo)
    unclaimed_death_cases = Case.objects.filter(case_type__name='Death Intimation', family_pension_claim__claim_status='pending')
    
    context = {
        'user_profile': user_profile,
        'my_cases': my_cases,
        'total_cases': total_cases,
        'pending_cases': pending_cases,
        'completed_cases': completed_cases,
        'overdue_cases': overdue_cases,
        'high_priority': high_priority,
        'medium_priority': medium_priority,
        'low_priority': low_priority,
        'recent_cases': recent_cases,
        'stage_stats': stage_stats,
        'unclaimed_death_cases': unclaimed_death_cases,
    }
    
    return render(request, 'cases/dashboard.html', context)

@login_required
def case_list(request):
    """List all cases with filtering and search"""
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    # Base queryset
    cases = Case.objects.all()
    
    # Filter by user role
    if user_profile.role != 'ADMIN':
        cases = cases.filter(current_holder=user_profile)
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        cases = cases.filter(
            Q(case_id__icontains=search_query) |
            Q(case_title__icontains=search_query) |
            Q(applicant_name__icontains=search_query)
        )
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter:
        if status_filter == 'completed':
            cases = cases.filter(is_completed=True)
        elif status_filter == 'pending':
            cases = cases.filter(is_completed=False)
        elif status_filter == 'overdue':
            cases = cases.filter(
                is_completed=False,
                expected_completion__lt=timezone.now()
            )
    
    # Filter by priority
    priority_filter = request.GET.get('priority', '')
    if priority_filter:
        cases = cases.filter(priority=priority_filter)
    
    # Filter by case type
    case_type_filter = request.GET.get('case_type', '')
    if case_type_filter:
        cases = cases.filter(case_type_id=case_type_filter)
    
    # Pagination
    paginator = Paginator(cases, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'priority_filter': priority_filter,
        'case_type_filter': case_type_filter,
        'case_types': CaseType.objects.all(),
        'user_profile': user_profile,
    }
    
    return render(request, 'cases/case_list.html', context)

@login_required
def case_detail(request, case_id):
    """View case details and movement history"""
    case = get_object_or_404(Case, case_id=case_id)
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    # Check permissions
    if user_profile.role != 'ADMIN' and case.current_holder != user_profile:
        messages.error(request, "You don't have permission to view this case.")
        return redirect('case_list')
    
    # Get movement history
    movements = CaseMovement.objects.filter(case=case).order_by('-movement_date')
    
    # Get workflow information
    workflow = get_workflow_for_case(case)
    current_stage_index = get_current_stage_index(case, workflow)
    
    context = {
        'case': case,
        'movements': movements,
        'workflow': workflow,
        'current_stage_index': current_stage_index,
        'user_profile': user_profile,
    }
    
    return render(request, 'cases/case_detail.html', context)

@login_required
def register_case(request):
    """Register a new case"""
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    if request.method == 'POST':
        form = CaseRegistrationForm(request.POST)
        if form.is_valid():
            case = form.save(commit=False)
            case.created_by = request.user
            case.last_updated_by = request.user
            
            # Set initial holder from form
            initial_holder = form.cleaned_data['initial_holder']
            case.current_holder = initial_holder
            case.current_status = f"With {initial_holder.user.username}"
            case.case_title = f"{case.case_type.name} - {case.sub_category}"
            
            # Handle PPO lookup
            ppo_number = form.cleaned_data.get('ppo_number')
            if ppo_number:
                try:
                    ppo = PPOMaster.objects.get(ppo_number=ppo_number)
                    case.ppo_master = ppo
                    case.applicant_name = ppo.name
                except PPOMaster.DoesNotExist:
                    pass
            
            # For Superannuation, set date_of_retirement
            if case.case_type.name == 'Superannuation' and case.retiring_employee:
                case.date_of_retirement = case.retiring_employee.retirement_date
            
            case.save()
            
            # Create initial movement record
            CaseMovement.objects.create(
                case=case,
                from_stage='New',
                to_stage=initial_holder.role,
                to_holder=initial_holder,
                action='Case registered',
                updated_by=request.user
            )
            
            # For Death Intimation, create claim (fixed typo and adjusted fields)
            if case.case_type.name == 'Death Intimation':
                FamilyPensionClaim.objects.create(
                    case=case,
                    claim_received=form.cleaned_data.get('date_of_death'),
                    eligible_claimant=None,  # No direct field; set to None or create FamilyMember if needed
                    ppo_master=case.ppo_master,
                    created_by=request.user
                )
            
            messages.success(request, f'Case {case.case_id} registered successfully!')
            return redirect('case_detail', case_id=case.case_id)
    else:
        form = CaseRegistrationForm()
    
    return render(request, 'cases/register_case.html', {'form': form})

@login_required
def move_case(request, case_id):
    """Move case to next/previous stage or reassign"""
    case = get_object_or_404(Case, case_id=case_id)
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    # Check permissions
    if user_profile.role != 'ADMIN' and case.current_holder != user_profile:
        messages.error(request, "You don't have permission to move this case.")
        return redirect('case_detail', case_id=case_id)
    
    preview_message = ""
    pre_type = request.GET.get('type') if request.method == 'GET' else None
    
    if request.method == 'GET' and pre_type:
        workflow = get_workflow_for_case(case)
        current_index = get_current_stage_index(case, workflow)
        
        if pre_type == 'forward':
            if current_index < len(workflow) - 1:
                next_stage = workflow[current_index + 1]
                holders = UserProfile.objects.filter(role=next_stage, is_active_holder=True)
                if holders.exists():
                    preview_message = f"Select from available holders in {next_stage} stage."
                else:
                    preview_message = f"No available holders in next stage: {next_stage}."
            else:
                preview_message = "Case is already at the final stage."
        elif pre_type == 'backward':
            if current_index > 0:
                prev_stage = workflow[current_index - 1]
                holders = UserProfile.objects.filter(role=prev_stage, is_active_holder=True)
                if holders.exists():
                    preview_message = f"Select from available holders in {prev_stage} stage."
                else:
                    preview_message = f"No available holders in previous stage: {prev_stage}."
            else:
                preview_message = "Case is already at the first stage."
        elif pre_type == 'complete':
            preview_message = "This will mark the case as completed."
        elif pre_type == 'reassign':
            preview_message = "Select a new holder in the same stage to re-assign."
    
    if request.method == 'POST':
        form = CaseMovementForm(request.POST, case=case)
        if form.is_valid():
            movement_type = form.cleaned_data['movement_type']
            comments = form.cleaned_data['comments']
            to_holder = form.cleaned_data.get('to_holder')
            workflow = get_workflow_for_case(case)
            current_index = get_current_stage_index(case, workflow)
            from_holder = case.current_holder
            from_stage = from_holder.role
            
            # Calculate days in previous stage
            delta = timezone.now() - case.last_update_date
            days_prev = delta.days
            
            to_stage = None
            action = None
            
            if movement_type in ['forward', 'backward', 'reassign']:
                if not to_holder:
                    messages.error(request, "Please select a holder.")
                    return redirect('case_detail', case_id=case_id)
                to_stage = to_holder.role
            
            if movement_type == 'forward':
                if current_index >= len(workflow) - 1:
                    messages.error(request, "Case is already at the final stage.")
                    return redirect('case_detail', case_id=case_id)
                expected_stage = workflow[current_index + 1]
                if to_stage != expected_stage:
                    messages.error(request, "Selected holder must be in the next stage.")
                    return redirect('case_detail', case_id=case_id)
                action = 'Moved forward'
                if current_index + 1 == len(workflow) - 1:
                    case.is_completed = True
                    case.actual_completion = timezone.now()
                    case.current_status = 'Completed'
                else:
                    case.current_status = f"With {to_holder.user.username}"
            elif movement_type == 'backward':
                if current_index <= 0:
                    messages.error(request, "Case is already at the first stage.")
                    return redirect('case_detail', case_id=case_id)
                expected_stage = workflow[current_index - 1]
                if to_stage != expected_stage:
                    messages.error(request, "Selected holder must be in the previous stage.")
                    return redirect('case_detail', case_id=case_id)
                action = 'Moved backward'
                if case.is_completed:
                    case.is_completed = False
                    case.actual_completion = None
                case.current_status = f"With {to_holder.user.username}"
            elif movement_type == 'reassign':
                if to_stage != from_stage:
                    messages.error(request, "New holder must be in the same stage.")
                    return redirect('case_detail', case_id=case_id)
                action = 'Re-assigned'
                case.current_status = f"With {to_holder.user.username}"
            elif movement_type == 'complete':
                if current_index < 1:  # DH is index 0, not allowed
                    messages.error(request, "Cases can only be completed from AAO onwards.")
                    return redirect('case_detail', case_id=case_id)
                to_holder = from_holder  # Keep current holder
                to_stage = 'Completed'
                action = 'Marked as Completed'
                case.is_completed = True
                case.actual_completion = timezone.now()
                case.current_status = 'Completed'
            
            # Update case
            case.days_in_current_stage = 0
            case.total_days_pending += days_prev
            if to_holder:
                case.current_holder = to_holder
            case.status_color = get_status_color(to_stage or from_stage, case.priority) if to_stage != 'Completed' else 'Blue'
            case.last_updated_by = request.user
            case.last_update_date = timezone.now()
            case.save()
            
            # Log movement
            CaseMovement.objects.create(
                case=case,
                from_stage=from_stage,
                to_stage=to_stage or from_stage,
                from_holder=from_holder,
                to_holder=to_holder,
                action=action,
                comments=comments,
                days_in_previous_stage=days_prev,
                updated_by=request.user
            )
            
            messages.success(request, f"Case updated successfully.")
            return redirect('case_detail', case_id=case_id)
    else:
        initial = {'movement_type': pre_type}
        form = CaseMovementForm(case=case, initial=initial)
    
    return render(request, 'cases/move_case.html', {
        'form': form, 
        'case': case,
        'preview_message': preview_message,
    })

@require_http_methods(["GET"])
def get_ppo_data(request):
    ppo_number = request.GET.get('ppo_number')
    if not ppo_number:
        return JsonResponse({'error': 'No PPO number provided'}, status=400)
    try:
        ppo = PPOMaster.objects.get(ppo_number=ppo_number)
        data = {
            'name': ppo.name,
            'designation': ppo.designation,
            'department': ppo.department,
            'mobile': ppo.phone,  # Assuming phone is mobile
            'last_lc': ppo.last_lc_done_date.strftime('%d-%m-%Y') if ppo.last_lc_done_date else '',
            'kyp': ppo.kyp_flag,
        }
        return JsonResponse(data)
    except PPOMaster.DoesNotExist:
        return JsonResponse({'error': 'PPO not found'}, status=404)

@require_http_methods(["GET"])
def get_sub_categories(request):
    case_type_id = request.GET.get('case_type_id')
    if not case_type_id:
        return JsonResponse({'sub_categories': []})
    try:
        case_type = CaseType.objects.get(id=case_type_id)
        sub_cats = case_type.get_sub_categories_list()
        return JsonResponse({'sub_categories': sub_cats})
    except CaseType.DoesNotExist:
        return JsonResponse({'sub_categories': []})

@require_http_methods(["GET"])
def get_retiring_employee_data(request):
    employee_id = request.GET.get('employee_id')
    if not employee_id:
        return JsonResponse({'error': 'No employee ID provided'}, status=400)
    try:
        employee = RetiringEmployee.objects.get(id=employee_id)
        data = {
            'retirement_date': employee.retirement_date.strftime('%d-%m-%Y') if employee.retirement_date else '',
            # Add more fields if needed, e.g., name if not already selected
        }
        return JsonResponse(data)
    except RetiringEmployee.DoesNotExist:
        return JsonResponse({'error': 'Employee not found'}, status=404)

@require_http_methods(["GET"])
def get_retiring_employees_by_month_year(request):
    month = request.GET.get('month')
    year = request.GET.get('year')
    if not month or not year:
        return JsonResponse({'employees': []})
    try:
        month = int(month)
        year = int(year)
        from_date = date(year, month, 1)
        to_date = (from_date + relativedelta(months=1)) - timedelta(days=1)
        employees = RetiringEmployee.objects.filter(
            retirement_date__gte=from_date,
            retirement_date__lte=to_date
        ).values('id', 'name')
        return JsonResponse({'employees': list(employees)})
    except ValueError:
        return JsonResponse({'employees': []})

def register_user(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'User registered successfully!')
            return redirect('dashboard')
    else:
        form = UserRegistrationForm()
    return render(request, 'registration/register.html', {'form': form})

@login_required
def bulk_import_cases(request):
    if request.method == 'POST':
        form = BulkImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            if not csv_file.name.endswith('.csv'):
                messages.error(request, 'Please upload a CSV file.')
                return redirect('bulk_import_cases')
            decoded_file = csv_file.read().decode('utf-8').splitlines()
            reader = csv.DictReader(decoded_file)
            imported = 0
            skipped = 0
            for row in reader:
                case_id = row.get('Case_ID')
                if Case.objects.filter(case_id=case_id).exists():
                    skipped += 1
                    continue
                try:
                    case_type_name = row.get('Case_Type')
                    case_type = CaseType.objects.get(name=case_type_name)
                    sub_category = row.get('Sub_Category', '')
                    case_description = row.get('Case_Description', '')
                    applicant_name = row.get('Applicant_Name')
                    priority = row.get('Priority_Level')
                    current_status = row.get('Current_Status')
                    current_holder_username = row.get('Current_Holder')
                    current_holder = UserProfile.objects.get(user__username=current_holder_username)
                    days_in_current_stage = int(row.get('Days_in_Current_Stage', 0))
                    total_days_pending = int(row.get('Total_Days_Pending', 0))
                    registration_date = datetime.strptime(row['Registration_Date'], '%Y-%m-d %H:%M:%S') if row['Registration_Date'] else timezone.now()
                    expected_completion = datetime.strptime(row['Expected_Completion'], '%Y-%m-d %H:%M:%S') if row['Expected_Completion'] else timezone.now() + timedelta(days=30)
                    actual_completion = datetime.strptime(row['Actual_Completion'], '%Y-m-d %H:%M:%S') if row['Actual_Completion'] else None
                    status_color = row.get('Status_Color', 'Green')
                    is_completed = bool(row.get('Is_Completed', False))
                    last_update_date = datetime.strptime(row['Last_Update_Date'], '%Y-m-d %H:%M:%S') if row['Last_Update_Date'] else timezone.now()
                    
                    case = Case(
                        case_id=case_id,
                        registration_date=registration_date,
                        case_type=case_type,
                        sub_category=sub_category,
                        case_title=f"{case_type.name} - {sub_category}",
                        case_description=case_description,
                        applicant_name=applicant_name,
                        priority=priority,
                        current_status=current_status,
                        current_holder=current_holder,
                        days_in_current_stage=days_in_current_stage,
                        total_days_pending=total_days_pending,
                        expected_completion=expected_completion,
                        actual_completion=actual_completion,
                        status_color=status_color,
                        is_completed=is_completed,
                        created_by=request.user,
                        last_updated_by=request.user,
                        last_update_date=last_update_date
                    )
                    case.save()
                    imported += 1
                    
                    CaseMovement.objects.create(
                        case=case,
                        from_stage='New',
                        to_stage=current_holder.role,
                        to_holder=current_holder,
                        action='Imported from CSV',
                        updated_by=request.user
                    )
                except Exception as e:
                    print(f"Error importing {case_id}: {e}")
            messages.success(request, f'Imported {imported} cases, skipped {skipped}.')
            return redirect('case_list')
    else:
        form = BulkImportForm()
    return render(request, 'cases/bulk_import.html', {'form': form})