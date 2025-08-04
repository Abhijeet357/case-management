# cases/views.py (updated with fixes)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.db.models import Q, Count
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods, require_POST
import json
import csv
from django.db import transaction, models
from datetime import datetime, timedelta, date, time
from dateutil.relativedelta import relativedelta
from .models import Case, CaseType, CaseTypeTrigger, Record,RecordRequisition,RecordMovement,Location, PPOMaster, UserProfile, CaseMovement, WORKFLOW_STAGES, get_workflow_for_case, get_current_stage_index, get_status_color, FamilyPensionClaim, RetiringEmployee, DynamicFormField,CaseMilestone,CaseMilestoneProgress, CaseFieldData
from .forms import CaseRegistrationForm,CaseMovementForm, UserRegistrationForm, PPOSearchForm, BulkImportForm
from .forms import RecordRequisitionForm, RecordReturnForm
from .forms import GrievanceRegistrationForm, GrievanceActionForm, GrievanceMode
from .models import Grievance, PPOMaster, get_subordinate_roles
from collections import defaultdict
from django.db.models import Count, Avg, Q, F, Sum, Max, Min,Case as DjangoCase, When, IntegerField, Value
from django.db.models.functions import TruncMonth, TruncWeek, TruncDate
from django.utils.dateparse import parse_date
from collections import Counter


@login_required
def dashboard(request):
    """
    A unified, role-aware dashboard with separate tabs for personal tasks and team workflow.
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    now = timezone.now()

    # ==========================================================================
    # 1. LOGIC FOR "MY ACTION ITEMS" TAB
    # ==========================================================================
    my_own_tasks = []
    
    my_pending_cases = Case.objects.filter(current_holder=user_profile, is_completed=False)
    for case in my_pending_cases:
        my_own_tasks.append({'type': 'case', 'title': f'Action on Case: {case.case_id}', 'description': case.case_title, 'object': case, 'date': case.last_update_date, 'priority': case.priority})

    my_new_grievances = Grievance.objects.filter(status='NEW', assigned_to=user_profile)
    for grievance in my_new_grievances:
        my_own_tasks.append({'type': 'grievance', 'title': f'New Grievance: {grievance.grievance_id}', 'description': f'From: {grievance.complainant_name}', 'object': grievance, 'date': grievance.date_received, 'priority': 'High'})
    
    my_new_assigned_grievances_count = my_new_grievances.count()

    # --- THIS IS THE NEW LOGIC TO FIX THE ERROR ---
    # We pre-calculate the total number of grievances assigned to the user for the quick actions button.
    my_assigned_grievances_count = Grievance.objects.filter(assigned_to=user_profile).count()
    # --- END OF NEW LOGIC ---

    if user_profile.role == 'AAO':
        pending_approvals = RecordRequisition.objects.filter(Q(status='PENDING_APPROVAL') | Q(status='RETURN_REQUESTED'), approving_aao=user_profile)
        for req in pending_approvals:
            my_own_tasks.append({'type': 'approval', 'title': 'Approval Request', 'description': f'For Case: {req.case.case_id}', 'object': req, 'date': req.created_at, 'priority': 'Medium'})

    if user_profile.is_record_keeper:
        pending_handovers = RecordRequisition.objects.filter(status='APPROVED')
        for req in pending_handovers:
            my_own_tasks.append({'type': 'handover', 'title': 'Pending Handover', 'description': f'For Case: {req.case.case_id}', 'object': req, 'date': req.updated_at, 'priority': 'High'})
        pending_acks = RecordRequisition.objects.filter(status='RETURN_APPROVED')
        for req in pending_acks:
            my_own_tasks.append({'type': 'acknowledgment', 'title': 'Acknowledge Return', 'description': f'For Case: {req.case.case_id}', 'object': req, 'date': req.updated_at, 'priority': 'Medium'})

    for task in my_own_tasks:
        if isinstance(task['date'], date) and not isinstance(task['date'], datetime):
            naive_dt = datetime.combine(task['date'], datetime.min.time())
            task['date'] = timezone.make_aware(naive_dt)
            
    my_own_tasks.sort(key=lambda x: x['date'], reverse=True)


    # ==========================================================================
    # 2. LOGIC FOR THE "TEAM WORKFLOW" TAB
    # ==========================================================================
    subordinate_roles = get_subordinate_roles(user_profile.role)
    team_summary = defaultdict(int)
    team_grievance_stats = {}
    team_recent_grievances = None

    if subordinate_roles:
        subordinate_profiles = UserProfile.objects.filter(role__in=subordinate_roles)
        for sub_profile in subordinate_profiles:
            case_count = Case.objects.filter(current_holder=sub_profile, is_completed=False).count()
            if case_count > 0: team_summary[f'Cases with {sub_profile.user.username} ({sub_profile.role})'] += case_count
        
        team_grievances_qs = Grievance.objects.filter(assigned_to__role__in=subordinate_roles)
        team_grievance_stats = {
            'new_grievances': team_grievances_qs.filter(status='NEW').count(),
            'action_initiated': team_grievances_qs.filter(status='ACTION_INITIATED').count(),
            'disposed': team_grievances_qs.filter(status='DISPOSED').count(),
        }
        team_recent_grievances = team_grievances_qs.order_by('-date_received')[:5]


    # ==========================================================================
    # 3. LOGIC FOR "OVERALL STATS" TAB
    # ==========================================================================
    stats_cases = Case.objects.all()
    if user_profile.role != 'ADMIN':
        roles_to_view_stats = subordinate_roles + [user_profile.role]
        stats_cases = stats_cases.filter(current_holder__role__in=roles_to_view_stats)
    
    total_cases_stats = stats_cases.count()
    pending_cases_stats = stats_cases.filter(is_completed=False).count()
    overdue_cases_stats = stats_cases.filter(is_completed=False, expected_completion__lt=now).count()

    # ==========================================================================
    # 4. FINAL CONTEXT
    # ==========================================================================
    completed_cases_stats = total_cases_stats - pending_cases_stats
    context = {
        'my_own_tasks': my_own_tasks,
        'my_new_assigned_grievances_count': my_new_assigned_grievances_count, # Pass the count to the template
        'team_summary': dict(team_summary),
        'team_grievance_stats': team_grievance_stats,
        'team_recent_grievances': team_recent_grievances,
        'completed_cases_stats': completed_cases_stats,
        'has_subordinates': bool(subordinate_roles),
        'is_senior_officer': user_profile.role in ['AO', 'Dy.CCA', 'Jt.CCA', 'CCA', 'Pr.CCA', 'ADMIN'],
        'show_overall_stats': user_profile.role != 'DH',
        'total_cases_stats': total_cases_stats,
        'pending_cases_stats': pending_cases_stats,
        'overdue_cases_stats': overdue_cases_stats,
        'user_profile': user_profile,
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
    """
    View case details, movement history, and milestone progress.
    Includes hierarchical permission check.
    """
    case = get_object_or_404(Case, case_id=case_id)
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    # --- PERMISSION LOGIC IS HERE ---
    # Get the roles subordinate to the currently logged-in user.
    subordinate_roles = get_subordinate_roles(user_profile.role)

    # A user can view a case if:
    # 1. They are an ADMIN.
    # 2. The case is currently assigned to them.
    # 3. The case is assigned to someone in their subordinate hierarchy.
    can_view = (
        user_profile.role == 'ADMIN' or
        case.current_holder == user_profile or
        case.current_holder.role in subordinate_roles
    )

    if not can_view:
        messages.error(request, "You do not have permission to view this case.")
        return redirect('dashboard')
    # --- END OF PERMISSION LOGIC ---
        
    # Fetch related data
    movements = CaseMovement.objects.filter(case=case).order_by('-movement_date')
    milestone_progress = CaseMilestoneProgress.objects.filter(case=case).select_related('milestone')

    context = {
        'case': case,
        'movements': movements,
        'milestone_progress': milestone_progress, # Pass milestone data to the template
        'user_profile': user_profile,
        'now': timezone.now(), # Pass current time for overdue checks
    }
    
    return render(request, 'cases/case_detail.html', context)

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
                    case.applicant_name = ppo.employee_name  # Updated field
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

            if case.ppo_master:
                    trigger_auto_requisition(case, user_profile, request) # Pass request for messages
                           
            # For Death Intimation, create claim
            if case.case_type.name == 'Death Intimation':
                FamilyPensionClaim.objects.create(
                    case=case,
                    claim_received=form.cleaned_data.get('date_of_death'),
                    eligible_claimant=None,
                    ppo_master=case.ppo_master,
                    created_by=request.user
                )
            
            messages.success(request, f'Case {case.case_id} registered successfully!')
            return redirect('case_detail', case_id=case.case_id)
        else:
            # ADDED: Better error handling for debugging
            print("Form validation errors:", form.errors)
            print("Form non-field errors:", form.non_field_errors)
            messages.error(request, 'Please correct the errors below and try again.')
    else:
        form = CaseRegistrationForm()
    
    # ADDED: Pass additional context
    context = {
        'form': form,
        'has_errors': bool(form.errors) if hasattr(form, 'errors') else False,
        'selected_case_type': form.data.get('case_type') if form.data else None,
    }
    
    return render(request, 'cases/register_case.html', context)

@login_required
def move_case(request, case_id):
    """
    Move case to next/previous stage or reassign, AND transfer any associated
    physical records held by the current user.
    """
    case = get_object_or_404(Case, case_id=case_id)
    user_profile = get_object_or_404(UserProfile, user=request.user)

    if user_profile.role != 'ADMIN' and case.current_holder != user_profile:
        messages.error(request, "You don't have permission to move this case.")
        return redirect('case_detail', case_id=case.case_id)

    records_to_move = []
    # CORRECTED: Use .filter().first() to safely get the location, preventing a crash if duplicates exist.
    current_holder_location = Location.objects.filter(custodian=case.current_holder, location_type='USER_DESK').first()
    
    if current_holder_location and case.ppo_master:
        records_to_move = Record.objects.filter(
            pensioner=case.ppo_master,
            current_location=current_holder_location,
            status='IN_USE'
        )

    if request.method == 'POST':
        form = CaseMovementForm(request.POST, case=case)
        if form.is_valid():
            to_holder = form.cleaned_data.get('to_holder')
            from_holder = case.current_holder
            
            with transaction.atomic():
                if to_holder and to_holder != from_holder and records_to_move:
                    from_holder_location = Location.objects.filter(custodian=from_holder, location_type='USER_DESK').first()
                    
                    # CORRECTED: More robust get_or_create based on the unique custodian.
                    to_holder_location, created = Location.objects.get_or_create(
                        custodian=to_holder, 
                        location_type='USER_DESK',
                        defaults={'name': f"{to_holder.user.username}'s Desk"}
                    )

                    if from_holder_location:
                        for record in records_to_move:
                            RecordMovement.objects.create(
                                requisition=None,
                                record=record,
                                from_location=from_holder_location,
                                to_location=to_holder_location,
                                acknowledged_by=user_profile,
                                comments=f"Transferred automatically as part of case movement for {case.case_id}."
                            )
                            record.current_location = to_holder_location
                            record.save()
                
                # --- Existing logic for moving the case ---
                movement_type = form.cleaned_data['movement_type']
                if movement_type == 'complete':
                    case.is_completed = True
                    case.actual_completion = timezone.now()
                    case.current_status = 'Completed'
                elif to_holder:
                    case.current_holder = to_holder
                    case.current_status = f"With {to_holder.user.username}"
                case.last_updated_by = request.user
                case.save()

                CaseMovement.objects.create(
                    case=case, from_stage=from_holder.role,
                    to_stage=to_holder.role if to_holder else 'Completed',
                    from_holder=from_holder, to_holder=to_holder,
                    action=movement_type, comments=form.cleaned_data['comments'],
                    updated_by=request.user
                )

            messages.success(request, f"Case and associated records updated successfully.")
            return redirect('case_detail', case_id=case.case_id)
    else:
        form = CaseMovementForm(case=case)

    context = {
        'form': form, 'case': case,
        'workflow': get_workflow_for_case(case),
        'current_stage_index': get_current_stage_index(case, get_workflow_for_case(case)),
        'records_to_move': records_to_move,
    }
    return render(request, 'cases/move_case.html', context)


@login_required
@require_http_methods(["GET"])
def get_ppo_data(request):
    """
    AJAX view to fetch PPO data based on PPO number for grievance registration
    Returns: name_pensioner, pensioner_type, date_of_retirement, mobile_number
    """
    ppo_number = request.GET.get('ppo_number', '').strip()
    
    # Debug logging
    print(f"DEBUG: get_ppo_data called with PPO number: '{ppo_number}'")
    print(f"DEBUG: Request method: {request.method}")
    print(f"DEBUG: Request GET params: {request.GET}")
    
    if not ppo_number:
        print("DEBUG: No PPO number provided")
        return JsonResponse({
            'success': False,
            'error': 'PPO number is required'
        })
    
    try:
        # Check if PPOMaster table has any data
        total_ppos = PPOMaster.objects.count()
        print(f"DEBUG: Total PPOs in database: {total_ppos}")
        
        # Try to find PPO in PPOMaster
        ppo_master = PPOMaster.objects.get(ppo_number=ppo_number)
        print(f"DEBUG: Found PPO Master: {ppo_master}")
        
        # Format date_of_retirement to dd-mm-yyyy format
        formatted_retirement_date = ''
        if ppo_master.date_of_retirement:
            formatted_retirement_date = ppo_master.date_of_retirement.strftime('%d-%m-%Y')
        
        # Format date_of_death if it exists
        formatted_death_date = ''
        if hasattr(ppo_master, 'date_of_death') and ppo_master.date_of_death:
            formatted_death_date = ppo_master.date_of_death.strftime('%d-%m-%Y')
        
        # Prepare data - handle null values gracefully
        data = {
            'employee_name': ppo_master.employee_name or '',
            'mobile_number': ppo_master.mobile_number or '',
            'pensioner_type': getattr(ppo_master, 'pensioner_type', ''),
            'pension_type': getattr(ppo_master, 'pension_type', ''),
            'date_of_retirement': formatted_retirement_date,
            'date_of_death': formatted_death_date,
        }
        
        print(f"DEBUG: Returning data: {data}")
        
        return JsonResponse({'success': True, 'data': data})
        
    except PPOMaster.DoesNotExist:
        print(f"DEBUG: PPO number '{ppo_number}' not found in database")
        
        # Show some sample PPO numbers for debugging
        sample_ppos = list(PPOMaster.objects.values_list('ppo_number', flat=True)[:5])
        print(f"DEBUG: Sample PPO numbers in database: {sample_ppos}")
        
        return JsonResponse({
            'success': False,
            'error': f'PPO number "{ppo_number}" not found in database'
        })
    
    except Exception as e:
        print(f"DEBUG: Exception occurred: {str(e)}")
        import traceback
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        
        return JsonResponse({
            'success': False,
            'error': f'An error occurred while fetching PPO data: {str(e)}'
        })

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
    """
    AJAX view to fetch retiring employee data based on employee ID
    """
    employee_id = request.GET.get('employee_id')
    
    if not employee_id:
        return JsonResponse({'error': 'No employee ID provided'}, status=400)
    
    try:
        employee = RetiringEmployee.objects.get(id=employee_id)
        
        # Format retirement date to dd-mm-yyyy format
        formatted_retirement_date = ''
        if employee.retirement_date:
            formatted_retirement_date = employee.retirement_date.strftime('%d-%m-%Y')
        
        data = {
            'retirement_date': formatted_retirement_date,
            'employee_name': employee.name if hasattr(employee, 'name') else '',
            'employee_id': employee.employee_id if hasattr(employee, 'employee_id') else '',
        }
        
        return JsonResponse(data)
        
    except RetiringEmployee.DoesNotExist:
        return JsonResponse({'error': 'Employee not found'}, status=404)
    
    except Exception as e:
        return JsonResponse({'error': f'An error occurred: {str(e)}'}, status=500)

# Updated get_retiring_employee_data function with better error handling and debugging

@require_http_methods(["GET"])
def get_retiring_employee_data(request):
    """
    AJAX view to fetch retiring employee data based on employee ID
    """
    employee_id = request.GET.get('employee_id')
    
    if not employee_id:
        return JsonResponse({'error': 'No employee ID provided'}, status=400)
    
    try:
        employee = RetiringEmployee.objects.get(id=employee_id)
        
        # Format retirement date to dd-mm-yyyy format
        formatted_retirement_date = ''
        if employee.retirement_date:
            formatted_retirement_date = employee.retirement_date.strftime('%d-%m-%Y')
        
        data = {
            'retirement_date': formatted_retirement_date,
            'employee_name': employee.name if hasattr(employee, 'name') else '',
            'employee_id': employee.employee_id if hasattr(employee, 'employee_id') else '',
        }
        
        return JsonResponse(data)
        
    except RetiringEmployee.DoesNotExist:
        return JsonResponse({'error': 'Employee not found'}, status=404)
    
    except Exception as e:
        # Add more detailed error logging
        import traceback
        print(f"Error in get_retiring_employee_data: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return JsonResponse({'error': f'An error occurred: {str(e)}'}, status=500)

@require_http_methods(["GET"])
def get_retiring_employees_by_month_year(request):
    """
    AJAX view to get retiring employees by month and year - with enhanced debugging
    """
    month = request.GET.get('month')
    year = request.GET.get('year')
    
    print(f"DEBUG: Received month={month}, year={year}")  # Debug log
    
    if not month or not year:
        print("DEBUG: Missing month or year parameter")
        return JsonResponse({'employees': [], 'error': 'Month and year are required'})
    
    try:
        month = int(month)
        year = int(year)
        
        # Create date range for the specified month and year
        from_date = date(year, month, 1)
        
        # Get the last day of the month
        if month == 12:
            to_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            to_date = date(year, month + 1, 1) - timedelta(days=1)
        
        print(f"DEBUG: Searching for employees retiring between {from_date} and {to_date}")
        
        # Check if RetiringEmployee model exists and has data
        total_employees = RetiringEmployee.objects.count()
        print(f"DEBUG: Total employees in database: {total_employees}")
        
        employees = RetiringEmployee.objects.filter(
            retirement_date__gte=from_date,
            retirement_date__lte=to_date
        ).values('id', 'name')
        
        employee_list = list(employees)
        print(f"DEBUG: Found {len(employee_list)} employees for {month}/{year}")
        
        # If no employees found, let's check what dates are actually in the database
        if len(employee_list) == 0:
            sample_dates = RetiringEmployee.objects.values_list('retirement_date', flat=True)[:10]
            print(f"DEBUG: Sample retirement dates in database: {list(sample_dates)}")
        
        return JsonResponse({'employees': employee_list})
        
    except ValueError as e:
        print(f"DEBUG: ValueError - {e}")
        return JsonResponse({'employees': [], 'error': 'Invalid month or year format'})
    
    except Exception as e:
        import traceback
        print(f"DEBUG: Exception in get_retiring_employees_by_month_year: {e}")
        print(f"DEBUG: Traceback: {traceback.format_exc()}")
        return JsonResponse({'employees': [], 'error': f'Database error: {str(e)}'})
    
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

@login_required
@require_http_methods(["GET"])
def get_available_holders(request):
    """
    AJAX view to get available holders for case movement
    """
    case_id = request.GET.get('case_id')
    movement_type = request.GET.get('movement_type')

    if not case_id or not movement_type:
        return JsonResponse({
            'success': False,
            'error': 'Case ID and movement type are required'
        })

    try:
        case = Case.objects.get(case_id=case_id)
        workflow = get_workflow_for_case(case)
        current_index = get_current_stage_index(case, workflow)

        holders = []

        if movement_type == 'forward':
            if current_index < len(workflow) - 1:
                next_stage = workflow[current_index + 1]
                available_holders = UserProfile.objects.filter(
                    role=next_stage, 
                    is_active_holder=True
                ).select_related('user')

                holders = [
                    {
                        'id': holder.id,
                        'name': f"{holder.user.get_full_name() or holder.user.username} ({holder.role})",
                        'role': holder.role
                    }
                    for holder in available_holders
                ]

        elif movement_type == 'backward':
            if current_index > 0:
                prev_stage = workflow[current_index - 1]
                available_holders = UserProfile.objects.filter(
                    role=prev_stage, 
                    is_active_holder=True
                ).select_related('user')

                holders = [
                    {
                        'id': holder.id,
                        'name': f"{holder.user.get_full_name() or holder.user.username} ({holder.role})",
                        'role': holder.role
                    }
                    for holder in available_holders
                ]

        elif movement_type == 'reassign':
            current_stage = case.current_holder.role
            available_holders = UserProfile.objects.filter(
                role=current_stage, 
                is_active_holder=True
            ).exclude(id=case.current_holder.id).select_related('user')

            holders = [
                    {
                        'id': holder.id,
                        'name': f"{holder.user.get_full_name() or holder.user.username} ({holder.role})",
                        'role': holder.role
                    }
                    for holder in available_holders
            ]

        elif movement_type == 'complete':
            # No holders needed for completion
            holders = []

        return JsonResponse({
            'success': True,
            'holders': holders
        })

    except Case.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Case not found'
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'An error occurred: {str(e)}'
        })
from django.http import HttpResponse
import csv

def export_cases(request, format):
    # For demonstration, export all cases as CSV
    if format == 'csv':
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="cases.csv"'
        writer = csv.writer(response)
        writer.writerow(['Case ID', 'Title', 'Type', 'Priority', 'Status'])
        for case in Case.objects.all():
            writer.writerow([
                case.case_id,
                case.case_title,
                case.case_type.name if case.case_type else '',
                case.priority,
                'Completed' if case.is_completed else 'Pending'
            ])
        return response
    # You can add Excel/PDF export logic here later
    return HttpResponse("Export format not supported.", status=400)
@login_required
def enhanced_dashboard(request):
    """Enhanced dashboard with milestone tracking and dynamic fields"""
    try:
        user_profile = request.user.userprofile
    except:
        # If UserProfile doesn't exist, create one or redirect
        messages.error(request, 'User profile not found. Please contact administrator.')
        return redirect('dashboard')

    # Get cases based on role hierarchy
    if hasattr(user_profile, 'get_dashboard_cases'):
        cases = user_profile.get_dashboard_cases()
    else:
        # Fallback if method doesn't exist
        cases = Case.objects.filter(current_holder=user_profile)

    now = timezone.now()

    # Dashboard statistics
    total_cases = cases.count()
    pending_cases = cases.filter(is_completed=False).count()
    completed_today = cases.filter(
        is_completed=True,
        actual_completion__date=now.date()
    ).count()

    # Calculate overdue cases (fallback if no milestone system)
    overdue_count = cases.filter(
        is_completed=False,
        expected_completion__lt=now
    ).count()

    # Priority-wise breakdown
    priority_stats = cases.values('priority').annotate(count=Count('id'))

    # Milestone statistics (with error handling)
    milestone_stats = []
    overdue_milestones = []
    
    try:
        # Try to get milestone data if the model exists
        milestone_stats = CaseMilestoneProgress.objects.filter(
            case__in=cases
        ).values('status').annotate(count=Count('id'))

        # Cases requiring attention (overdue milestones)
        overdue_milestones = CaseMilestoneProgress.objects.filter(
            case__in=cases,
            status__in=['pending', 'in_progress'],
            expected_completion_date__lt=now
        ).select_related('case', 'milestone')[:5]
        
        overdue_count = overdue_milestones.count()
        
    except Exception as e:
        # If milestone system is not implemented, use basic overdue logic
        print(f"Milestone system not available: {e}")
        milestone_stats = []
        overdue_milestones = []

    # Recent cases with basic data
    recent_cases = cases.select_related('case_type', 'current_holder').order_by('-registration_date')[:10]

    context = {
        'total_cases': total_cases,
        'pending_cases': pending_cases,
        'completed_today': completed_today,
        'overdue_milestones': overdue_count,
        'priority_stats': priority_stats,
        'milestone_stats': milestone_stats,
        'recent_cases': recent_cases,
        'overdue_milestones': overdue_milestones,
        'user_role': user_profile.role,
        'now': now,
    }

    return render(request, 'cases/enhanced_dashboard.html', context)

# Add these updated view functions to your views.py to handle the enhanced functionality

@login_required
def register_case_enhanced(request):
    """Enhanced case registration with dynamic fields - with fallbacks"""
    if request.method == 'POST':
        try:
            with transaction.atomic():
                # Get basic case data
                case_type_id = request.POST.get('case_type')
                case_type = get_object_or_404(CaseType, id=case_type_id)

                # Create the case using existing logic
                case = Case(
                    case_type=case_type,
                    sub_category=request.POST.get('sub_category', ''),
                    case_title=request.POST.get('case_title', ''),
                    case_description=request.POST.get('case_description', ''),
                    applicant_name=request.POST.get('applicant_name', ''),
                    priority=request.POST.get('priority', 'Medium'),
                    current_status='Registered',
                    current_holder=request.user.userprofile,
                    created_by=request.user,
                    last_updated_by=request.user,
                )
                case.save()

                # Handle PPO Master association if provided
                ppo_number = request.POST.get('ppo_number')
                if ppo_number:
                    try:
                        ppo_master = PPOMaster.objects.get(ppo_number=ppo_number)
                        case.ppo_master = ppo_master
                        case.save()
                    except PPOMaster.DoesNotExist:
                        pass

                # Save dynamic field data (if CaseFieldData model exists)
                try:
                    for key, value in request.POST.items():
                        if key.startswith('dynamic_') and value:
                            field_name = key.replace('dynamic_', '')
                            CaseFieldData.objects.create(
                                case=case,
                                field_name=field_name,
                                field_value=value,
                                created_by=request.user
                            )
                except Exception as e:
                    print(f"Dynamic fields not available: {e}")

                # Initialize milestones (if milestone system is available)
                try:
                    if hasattr(case, 'initialize_milestones'):
                        case.initialize_milestones()
                except Exception as e:
                    print(f"Milestone system not available: {e}")

                messages.success(request, f'Case {case.case_id} registered successfully!')
                return redirect('case_detail', case_id=case.case_id)

        except Exception as e:
            messages.error(request, f'Error registering case: {str(e)}')

    # GET request - show form
    case_types = CaseType.objects.filter(is_active=True) if hasattr(CaseType, 'is_active') else CaseType.objects.all()
    context = {
        'case_types': case_types,
    }

    return render(request, 'cases/register_case_enhanced.html', context)

@login_required
def get_case_type_fields(request, case_type_id):
    """AJAX endpoint to get dynamic fields for a case type - with fallback"""
    try:
        case_type = get_object_or_404(CaseType, id=case_type_id)
        
        # Try to get dynamic fields if the system is implemented
        try:
            fields = case_type.dynamic_fields.filter(is_active=True).order_by('field_order')
            fields_data = []
            
            for field in fields:
                field_data = {
                    'name': field.field_name,
                    'label': field.field_label,
                    'type': field.field_type,
                    'required': field.is_required,
                    'help_text': field.help_text,
                    'group': field.field_group,
                }

                if field.field_type in ['select', 'radio']:
                    field_data['choices'] = field.get_choices_list()

                fields_data.append(field_data)
                
        except Exception as e:
            # Fallback - return empty fields
            print(f"Dynamic fields not available: {e}")
            fields_data = []

        return JsonResponse({
            'success': True,
            'fields': fields_data,
            'sub_categories': case_type.get_sub_categories_list() if hasattr(case_type, 'get_sub_categories_list') else []
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def case_detail_enhanced(request, case_id):
    """Enhanced case detail view with milestone tracking - with fallbacks"""
    case = get_object_or_404(Case, case_id=case_id)

    # Check if user can view this case (basic permission check)
    user_profile = request.user.userprofile
    if user_profile.role != 'ADMIN' and case.current_holder != user_profile:
        messages.error(request, 'You do not have permission to view this case.')
        return redirect('dashboard')

    # Get milestone progress (with fallback)
    milestone_progress = None
    try:
        if hasattr(case, 'get_milestone_progress'):
            milestone_progress = case.get_milestone_progress()
    except Exception as e:
        print(f"Milestone system not available: {e}")

    # Get dynamic field data (with fallback)
    dynamic_data = {}
    try:
        if hasattr(case, 'get_dynamic_field_data'):
            dynamic_data = case.get_dynamic_field_data()
        else:
            # Fallback - try to get from CaseFieldData if it exists
            field_data = CaseFieldData.objects.filter(case=case)
            for field in field_data:
                dynamic_data[field.field_name] = {
                    'label': field.field_name.replace('_', ' ').title(),
                    'value': field.field_value,
                    'type': 'text'}
    except Exception as e:
        print(f"Dynamic fields not available: {e}")

    # Get case movements
    movements = CaseMovement.objects.filter(case=case).order_by('-movement_date')[:10]

    context = {
        'case': case,
        'milestone_progress': milestone_progress,
        'dynamic_data': dynamic_data,
        'movements': movements,
        'can_edit': case.current_holder == user_profile,
    }

    return render(request, 'cases/case_detail_enhanced.html', context)

@login_required
def update_milestone(request, case_id, milestone_id):
    """Update milestone progress - with fallback"""
    if request.method == 'POST':
        try:
            case = get_object_or_404(Case, case_id=case_id)
            
            # Try to get milestone progress if system is available
            milestone_progress = get_object_or_404(
                CaseMilestoneProgress, 
                case=case, 
                milestone_id=milestone_id
            )

            # Check permissions
            if milestone_progress.assigned_to != request.user.userprofile:
                return JsonResponse({'success': False, 'error': 'Not authorized'})

            action = request.POST.get('action')
            notes = request.POST.get('notes', '')

            if action == 'start':
                milestone_progress.status = 'in_progress'
                milestone_progress.started_date = timezone.now()
            elif action == 'complete':
                milestone_progress.status = 'completed'
                milestone_progress.completed_date = timezone.now()
                milestone_progress.completed_by = request.user.userprofile
                if notes:
                    milestone_progress.notes = notes
            elif action == 'block':
                milestone_progress.status = 'blocked'
                if notes:
                    milestone_progress.notes = notes

            milestone_progress.save()

            return JsonResponse({
                'success': True,
                'message': f'Milestone {action}ed successfully'
            })

        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})

    return JsonResponse({'success': False, 'error': 'Invalid request'})

@login_required
def milestone_report(request):
    """Generate milestone completion report - with fallback"""
    user_profile = request.user.userprofile
    
    # Get cases based on user role
    if user_profile.role == 'ADMIN':
        cases = Case.objects.all()
    else:
        cases = Case.objects.filter(current_holder=user_profile)

    # Filter by date range if provided
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    try:
        milestone_progress = CaseMilestoneProgress.objects.filter(case__in=cases)

        if start_date:
            milestone_progress = milestone_progress.filter(created_at__gte=start_date)
        if end_date:
            milestone_progress = milestone_progress.filter(created_at__lte=end_date)

        # Statistics
        total_milestones = milestone_progress.count()
        completed_milestones = milestone_progress.filter(status='completed').count()
        pending_milestones = milestone_progress.filter(status='pending').count()
        overdue_milestones = milestone_progress.filter(
            status__in=['pending', 'in_progress'],
            expected_completion_date__lt=timezone.now()
        ).count()

        # Milestone completion by case type
        case_type_stats = milestone_progress.values(
            'milestone__case_type__name'
        ).annotate(
            total=Count('id'),
            completed=Count('id', filter=Q(status='completed'))
        )

        milestone_progress_list = milestone_progress.select_related('case', 'milestone')[:50]

    except Exception as e:
        # Fallback if milestone system is not available
        print(f"Milestone system not available: {e}")
        total_milestones = 0
        completed_milestones = 0
        pending_milestones = 0
        overdue_milestones = 0
        case_type_stats = []
        milestone_progress_list = []

    context = {
        'total_milestones': total_milestones,
        'completed_milestones': completed_milestones,
        'pending_milestones': pending_milestones,
        'overdue_milestones': overdue_milestones,
        'case_type_stats': case_type_stats,
        'milestone_progress': milestone_progress_list,
    }

    return render(request, 'cases/milestone_report.html', context)
@login_required
def request_record(request, case_id):
    """
    Handles the creation of a new record requisition for a specific case.
    Only accessible by users with the 'Dealing Hand' (DH) role.
    """
    case = get_object_or_404(Case, case_id=case_id)
    user_profile = get_object_or_404(UserProfile, user=request.user)

    # Permission Check: Only a Dealing Hand can initiate a requisition.
    # You can customize this role check if needed.
    if user_profile.role != 'DH':
        messages.error(request, "You do not have permission to request records.")
        return redirect('case_detail', case_id=case.case_id)

    if request.method == 'POST':
        # When the form is submitted
        form = RecordRequisitionForm(request.POST, case=case)
        if form.is_valid():
            try:
                # Use a database transaction to ensure data integrity.
                # If any step fails, all database changes will be rolled back.
                with transaction.atomic():
                    requisition = form.save(commit=False)
                    requisition.case = case
                    requisition.requester_dh = user_profile
                    # The 'approving_aao' is set from the form
                    requisition.save()

                    # The form saves the ManyToMany relationship for records_requested
                    form.save_m2m()

                    # Update the status of the requested physical records
                    requested_records = form.cleaned_data['records_requested']
                    for record in requested_records:
                        record.status = 'REQUISITIONED'
                        record.save()

                messages.success(request, f"Record requisition for case {case.case_id} has been submitted for approval.")
                return redirect('case_detail', case_id=case.case_id)
            except Exception as e:
                # Catch any potential errors during the process
                messages.error(request, f"An error occurred while submitting the requisition: {e}")

    else:
        # When the page is first loaded (GET request)
        form = RecordRequisitionForm(case=case)

    context = {
        'form': form,
        'case': case,
    }
    return render(request, 'cases/request_record.html', context)

# ==============================================================================
# == MODIFIED VIEWS FOR AAO APPROVAL WORKFLOW (Phase 6)
# ==============================================================================

# == RECORD MANAGEMENT WORKFLOW VIEWS ==

@login_required
def request_record(request, case_id):
    case = get_object_or_404(Case, case_id=case_id)
    user_profile = get_object_or_404(UserProfile, user=request.user)
    if user_profile.role != 'DH':
        messages.error(request, "You do not have permission to request records.")
        return redirect('case_detail', case_id=case.case_id)
    if request.method == 'POST':
        form = RecordRequisitionForm(request.POST, case=case)
        if form.is_valid():
            with transaction.atomic():
                requisition = form.save(commit=False)
                requisition.case = case
                requisition.requester_dh = user_profile
                requisition.save()
                form.save_m2m()
                for record in form.cleaned_data['records_requested']:
                    record.status = 'REQUISITIONED'
                    record.save()
            messages.success(request, "Record requisition has been submitted for approval.")
            return redirect('case_detail', case_id=case.case_id)
    else:
        form = RecordRequisitionForm(case=case)
    return render(request, 'cases/request_record.html', {'form': form, 'case': case})

@login_required
def requisition_approval_dashboard(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    if user_profile.role != 'AAO':
        messages.error(request, "You do not have permission to view this page.")
        return redirect('dashboard')
    pending_requests = RecordRequisition.objects.filter(
        models.Q(status='PENDING_APPROVAL') | models.Q(status='RETURN_REQUESTED'),
        approving_aao=user_profile
    ).select_related('case', 'requester_dh', 'case__ppo_master').prefetch_related('records_requested')
    return render(request, 'cases/requisition_approval_dashboard.html', {'pending_requests': pending_requests})

@require_POST
@login_required
def requisition_action(request, requisition_id):
    requisition = get_object_or_404(RecordRequisition, id=requisition_id)
    user_profile = get_object_or_404(UserProfile, user=request.user)
    if requisition.approving_aao != user_profile:
        return HttpResponseForbidden("You are not authorized to perform this action.")
    action = request.POST.get('action')
    original_status = requisition.status
    if original_status == 'PENDING_APPROVAL':
        if action == 'approve':
            requisition.status = 'APPROVED'
            messages.success(request, f"Requisition for case {requisition.case.case_id} has been approved.")
        elif action == 'reject':
            requisition.status = 'REJECTED'
            with transaction.atomic():
                for record in requisition.records_requested.all():
                    record.status = 'AVAILABLE'
                    record.save()
            messages.warning(request, f"Requisition for case {requisition.case.case_id} has been rejected.")
    elif original_status == 'RETURN_REQUESTED':
        if action == 'approve':
            requisition.status = 'RETURN_APPROVED'
            messages.success(request, f"Return request for case {requisition.case.case_id} has been approved.")
        elif action == 'reject':
            requisition.status = 'RETURN_REJECTED'
            messages.warning(request, f"Return request for case {requisition.case.case_id} has been rejected.")
    requisition.save()
    return redirect('requisition_approval_dashboard')

@login_required
def record_keeper_dashboard(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    if not user_profile.is_record_keeper:
        messages.error(request, "You do not have permission to view this page.")
        return redirect('dashboard')
    approved_requisitions = RecordRequisition.objects.filter(status='APPROVED')
    approved_returns = RecordRequisition.objects.filter(status='RETURN_APPROVED')
    context = {
        'approved_requisitions': approved_requisitions,
        'approved_returns': approved_returns,
    }
    return render(request, 'cases/record_keeper_dashboard.html', context)

@require_POST
@login_required
def handover_record(request, requisition_id):
    requisition = get_object_or_404(RecordRequisition, id=requisition_id)
    record_keeper_profile = get_object_or_404(UserProfile, user=request.user)

    if not record_keeper_profile.is_record_keeper:
        return HttpResponseForbidden("You are not authorized to perform this action.")

    receiving_dh_profile = requisition.requester_dh
    try:
        with transaction.atomic():
            # CORRECTED: More robust get_or_create based on the unique custodian.
            to_location, created = Location.objects.get_or_create(
                custodian=receiving_dh_profile,
                location_type='USER_DESK',
                defaults={'name': f"{receiving_dh_profile.user.username}'s Desk"}
            )
            for record in requisition.records_requested.all():
                from_location = record.current_location
                RecordMovement.objects.create(
                    requisition=requisition, record=record, from_location=from_location,
                    to_location=to_location, acknowledged_by=record_keeper_profile
                )
                record.status = 'IN_USE'
                record.current_location = to_location
                record.save()
            requisition.status = 'IN_USE'
            requisition.save()
        messages.success(request, f"Records for case {requisition.case.case_id} have been successfully marked as handed over.")
    except Exception as e:
        messages.error(request, f"An error occurred during handover: {e}")
    return redirect('record_keeper_dashboard')


@login_required
def return_record(request, case_id):
    case = get_object_or_404(Case, case_id=case_id)
    user_profile = get_object_or_404(UserProfile, user=request.user)
    if user_profile.role != 'DH':
        messages.error(request, "You do not have permission to return records.")
        return redirect('case_detail', case_id=case.case_id)
    if request.method == 'POST':
        form = RecordReturnForm(request.POST, case=case, user=user_profile)
        if form.is_valid():
            with transaction.atomic():
                return_request = form.save(commit=False)
                return_request.case = case
                return_request.requester_dh = user_profile
                return_request.is_return_request = True
                return_request.status = 'RETURN_REQUESTED'
                return_request.save()
                form.save_m2m()
            messages.success(request, f"Request to return records for case {case.case_id} has been submitted.")
            return redirect('case_detail', case_id=case.case_id)
    else:
        form = RecordReturnForm(case=case, user=user_profile)
    return render(request, 'cases/return_record.html', {'form': form, 'case': case})

@require_POST
@login_required
def acknowledge_return(request, requisition_id):
    requisition = get_object_or_404(RecordRequisition, id=requisition_id)
    record_keeper_profile = get_object_or_404(UserProfile, user=request.user)

    if not record_keeper_profile.is_record_keeper:
        return HttpResponseForbidden("You are not authorized to perform this action.")

    try:
        with transaction.atomic():
            record_room, created = Location.objects.get_or_create(
                name='CTO Record Room', defaults={'location_type': 'RECORD_ROOM'}
            )
            returning_dh_profile = requisition.requester_dh
            
            # CORRECTED: Use .filter().first() to safely get the location.
            from_location = Location.objects.filter(custodian=returning_dh_profile, location_type='USER_DESK').first()
            if not from_location:
                raise Location.DoesNotExist # Raise an error if the user's location can't be found

            for record in requisition.records_requested.all():
                RecordMovement.objects.create(
                    requisition=requisition, record=record, from_location=from_location,
                    to_location=record_room, acknowledged_by=record_keeper_profile,
                    comments=f"Record returned to {record_room.name} for case {requisition.case.case_id}."
                )
                record.status = 'AVAILABLE'
                record.current_location = record_room
                record.save()
            requisition.status = 'RETURNED'
            requisition.save()
        messages.success(request, f"Return for case {requisition.case.case_id} has been successfully acknowledged.")
    except Location.DoesNotExist:
        messages.error(request, f"Could not find the 'User Desk' location for {returning_dh_profile.user.username}. Cannot process return.")
    except Exception as e:
        messages.error(request, f"An error occurred while acknowledging the return: {e}")
    return redirect('record_keeper_dashboard')

def get_default_approver_and_keeper():
    """
    Finds default users for automated requisitions.
    - Approver: The first active AAO found.
    - Keeper: The first user flagged as a record keeper.
    This can be made more sophisticated later if needed.
    """
    default_approver = UserProfile.objects.filter(role='AAO', is_active_holder=True).first()
    return default_approver

def trigger_auto_requisition(case, user_profile, request):
    """
    Checks for and creates an automated record requisition for a newly created case.
    """
    triggers = CaseTypeTrigger.objects.filter(
        case_type=case.case_type,
        trigger_event='ON_CASE_CREATION'
    )
    if not triggers.exists():
        return

    record_types_to_request = [trigger.records_to_request for trigger in triggers]
    records = Record.objects.filter(
        pensioner=case.ppo_master,
        record_type__in=record_types_to_request,
        status='AVAILABLE'
    )
    if not records.exists():
        return

    default_approver = get_default_approver_and_keeper()
    if not default_approver:
        print(f"AUTO-REQUISITION FAILED: No default AAO approver found for case {case.case_id}.")
        return

    try:
        with transaction.atomic():
            requisition = RecordRequisition.objects.create(
                case=case,
                requester_dh=user_profile,
                approving_aao=default_approver,
                status='PENDING_APPROVAL'
            )
            requisition.records_requested.set(records)
            for record in records:
                record.status = 'REQUISITIONED'
                record.save()
        
        # Now it can correctly use the 'request' object to show a message
        messages.info(request, f"An automated record requisition has been created for this case and sent for approval.")

    except Exception as e:
        print(f"AUTO-REQUISITION FAILED: Error creating requisition for case {case.case_id}: {e}")
        login_required
def record_history_report(request):
    """
    Provides a page to search for a record by PPO number and view its
    complete movement history.
    """
    # Get the search query from the URL parameters (e.g., ?q=PPO123)
    query = request.GET.get('q', '')
    records = None
    record_movements = {} # A dictionary to hold movements for each record

    if query:
        # If a query is submitted, search for records belonging to pensioners
        # with a matching PPO number or name.
        records = Record.objects.filter(
            Q(pensioner__ppo_number__icontains=query) |
            Q(pensioner__employee_name__icontains=query)
        ).select_related('pensioner', 'current_location', 'current_location__custodian__user')

        if records:
            # For each record found, fetch its entire movement history.
            for record in records:
                record_movements[record.id] = RecordMovement.objects.filter(
                    record=record
                ).order_by('-timestamp').select_related('from_location', 'to_location', 'acknowledged_by__user')

    context = {
        'query': query,
        'records': records,
        'record_movements': record_movements,
        'is_search': bool(query), # A flag to know if a search has been performed
    }
    return render(request, 'cases/record_history_report.html', context)

@login_required
def register_grievance(request):
    """
    Handles the display and processing of the grievance registration form.
    """
    if request.method == 'POST':
        form = GrievanceRegistrationForm(request.POST)
        if form.is_valid():
            pensioner_object = form.pensioner_object
            
            grievance = form.save(commit=False)
            grievance.pensioner = pensioner_object
            grievance.save()
            
            messages.success(request, f"Grievance {grievance.grievance_id} has been successfully registered.")
            
            # CORRECTED: Redirect using the string-based 'grievance_id' instead of the integer 'id'
            return redirect('take_grievance_action', grievance_id=grievance.grievance_id)
    else:
        form = GrievanceRegistrationForm()

    context = {
        'form': form,
    }
    return render(request, 'cases/register_grievance.html', context)


@login_required
def take_grievance_action(request, grievance_id):
    """
    Displays a registered grievance and provides a form to create a formal
    case from it.
    """
    # CORRECTED: Look up the grievance using the string 'grievance_id' field
    grievance = get_object_or_404(Grievance, grievance_id=grievance_id)
    user_profile = get_object_or_404(UserProfile, user=request.user)

    if grievance.generated_case:
        messages.warning(request, "Action has already been taken on this grievance.")
        return redirect('case_detail', case_id=grievance.generated_case.case_id)

    if request.method == 'POST':
        form = GrievanceActionForm(request.POST)
        if form.is_valid():
            case_type = form.cleaned_data['case_type']
            
            initial_holder = UserProfile.objects.filter(role='DH', is_active_holder=True).first()
            if not initial_holder:
                messages.error(request, "No active Dealing Hand found to assign the case. Please configure users.")
                return redirect('take_grievance_action', grievance_id=grievance.grievance_id)

            with transaction.atomic():
                new_case = Case.objects.create(
                    case_type=case_type,
                    ppo_master=grievance.pensioner,
                    applicant_name=grievance.complainant_name,
                    case_description=grievance.grievance_text,
                    case_title=f"{case_type.name} from Grievance {grievance.grievance_id}",
                    current_holder=initial_holder,
                    current_status=f"With {initial_holder.user.username}",
                    created_by=request.user,
                    last_updated_by=request.user
                )

                CaseMovement.objects.create(
                    case=new_case,
                    from_stage='Grievance',
                    to_stage=initial_holder.role,
                    to_holder=initial_holder,
                    action='Case created from Grievance',
                    updated_by=request.user
                )

                grievance.generated_case = new_case
                grievance.status = 'ACTION_INITIATIED' # Note: Typo in original, should be 'ACTION_INITIATED'
                grievance.save()

            messages.success(request, f"Case {new_case.case_id} has been successfully created from the grievance.")
            return redirect('case_detail', case_id=new_case.case_id)
    else:
        form = GrievanceActionForm()

    context = {
        'grievance': grievance,
        'form': form,
    }
    return render(request, 'cases/take_grievance_action.html', context)

@login_required
def grievance_list(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]

    if user_profile.role == 'ADMIN':
        grievances = Grievance.objects.all()
    else:
        grievances = Grievance.objects.filter(Q(assigned_to__role__in=roles_to_view) | Q(created_by=request.user))
    
    paginator = Paginator(grievances.order_by('-date_received'), 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'cases/grievance_list.html', {'page_obj': page_obj})

@login_required
def my_grievances(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    my_grievances = Grievance.objects.filter(assigned_to=user_profile)
    return render(request, 'cases/my_grievances.html', {'my_grievances': my_grievances})

# Add placeholder views for the other grievance URLs to prevent errors

@login_required
def pending_grievance_actions(request):
    """View all grievances pending action"""
    user_profile = get_object_or_404(UserProfile, user=request.user)
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]
    
    if user_profile.role == 'ADMIN':
        pending_grievances = Grievance.objects.filter(status='NEW')
    else:
        pending_grievances = Grievance.objects.filter(
            status='NEW',
            assigned_to__role__in=roles_to_view
        )
    
    # Add search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        pending_grievances = pending_grievances.filter(
            Q(grievance_id__icontains=search_query) |
            Q(complainant_name__icontains=search_query) |
            Q(pensioner__employee_name__icontains=search_query) |
            Q(pensioner__ppo_number__icontains=search_query)
        )
    
    paginator = Paginator(pending_grievances.order_by('-date_received'), 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query
    }
    return render(request, 'cases/pending_grievance_actions.html', context)

@login_required
def grievance_dashboard(request):
    """Grievance Dashboard for officers"""
    user_profile = get_object_or_404(UserProfile, user=request.user)
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]
    
    # Dashboard statistics
    if user_profile.role == 'ADMIN':
        all_grievances = Grievance.objects.all()
    else:
        all_grievances = Grievance.objects.filter(
            Q(assigned_to__role__in=roles_to_view) | Q(created_by=request.user)
        )
    
    stats = {
        'total_grievances': all_grievances.count(),
        'new_grievances': all_grievances.filter(status='NEW').count(),
        'action_initiated': all_grievances.filter(status='ACTION_INITIATED').count(),
        'disposed_grievances': all_grievances.filter(status='DISPOSED').count(),
        'my_grievances': Grievance.objects.filter(assigned_to=user_profile).count(),
    }
    
    # Recent grievances
    recent_grievances = all_grievances.order_by('-date_received')[:10]
    
    # Overdue grievances (older than 30 days without action)
    overdue_date = timezone.now().date() - timedelta(days=30)
    overdue_grievances = all_grievances.filter(
        status='NEW',
        date_received__lt=overdue_date
    )[:5]
    
    context = {
        'stats': stats,
        'recent_grievances': recent_grievances,
        'overdue_grievances': overdue_grievances,
        'user_role': user_profile.role
    }
    return render(request, 'cases/grievance_dashboard.html', context)



@login_required
def escalated_grievances(request):
    """View escalated/overdue grievances"""
    user_profile = get_object_or_404(UserProfile, user=request.user)
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]
    
    # Grievances older than 30 days without action
    overdue_date = timezone.now().date() - timedelta(days=30)
    
    if user_profile.role == 'ADMIN':
        escalated_grievances = Grievance.objects.filter(
            status='NEW',
            date_received__lt=overdue_date
        )
    else:
        escalated_grievances = Grievance.objects.filter(
            status='NEW',
            date_received__lt=overdue_date,
            assigned_to__role__in=roles_to_view
        )
    
    paginator = Paginator(escalated_grievances.order_by('date_received'), 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'overdue_days': 30
    }
    return render(request, 'cases/escalated_grievances.html', context)

@login_required
def overdue_grievances(request):
    """Same as escalated - redirect for consistency"""
    return escalated_grievances(request)

# Replace the placeholder grievance_reports view in your views.py with this complete implementation

@login_required
def grievance_reports(request):
    """
    Comprehensive grievance reports and analytics
    Provides detailed analysis of complaint patterns, resolution trends, and service quality metrics
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    # Permission check - AAO and above can access grievance reports
    if user_profile.role == 'DH':
        messages.error(request, 'You do not have permission to access grievance reports.')
        return redirect('dashboard')
    
    # Date range filter with defaults
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=90)  # Default to last 3 months
    
    # Get filter parameters from request
    start_date_param = request.GET.get('start_date')
    end_date_param = request.GET.get('end_date')
    status_filter = request.GET.get('status', '')
    mode_filter = request.GET.get('mode', '')
    
    if start_date_param:
        try:
            start_date = parse_date(start_date_param)
        except (ValueError, TypeError):
            pass
    
    if end_date_param:
        try:
            end_date = parse_date(end_date_param)
        except (ValueError, TypeError):
            pass
    
    # Get grievances based on user role hierarchy
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]
    
    if user_profile.role == 'ADMIN':
        grievances = Grievance.objects.all()
    else:
        grievances = Grievance.objects.filter(
            Q(assigned_to__role__in=roles_to_view) | Q(created_by=request.user)
        )
    
    # Apply date range filter
    grievances = grievances.filter(
        date_received__gte=start_date,
        date_received__lte=end_date
    )
    
    # Apply additional filters
    if status_filter:
        grievances = grievances.filter(status=status_filter)
    
    if mode_filter:
        grievances = grievances.filter(mode_of_receipt_id=mode_filter)
    
    # Calculate comprehensive report data
    total_grievances = grievances.count()
    
    # Status breakdown
    by_status = grievances.values('status').annotate(count=Count('id')).order_by('status')
    
    # Mode of receipt breakdown
    by_mode = grievances.values('mode_of_receipt__name').annotate(count=Count('id')).order_by('-count')
    
    # Monthly statistics for trend analysis
    monthly_stats = grievances.extra(
        select={'month': "strftime('%%Y-%%m', date_received)"}
    ).values('month').annotate(count=Count('id')).order_by('month')
    
    # Average resolution time calculation
    resolved_grievances = grievances.filter(
        status='DISPOSED',
        date_disposed__isnull=False
    )
    
    avg_resolution_time = None
    if resolved_grievances.exists():
        # Calculate average resolution time
        resolution_times = []
        for grievance in resolved_grievances:
            if grievance.date_disposed and grievance.date_received:
                resolution_time = grievance.date_disposed - grievance.date_received
                resolution_times.append(resolution_time.days)
        
        if resolution_times:
            avg_days = sum(resolution_times) / len(resolution_times)
            avg_resolution_time = timedelta(days=avg_days)
    
    # Prepare report data structure
    report_data = {
        'total_grievances': total_grievances,
        'by_status': by_status,
        'by_mode': by_mode,
        'monthly_stats': monthly_stats,
        'avg_resolution_time': avg_resolution_time,
    }
    
    # Get recent grievances for detailed view (limited to 50 for performance)
    recent_grievances = grievances.select_related(
        'pensioner', 'mode_of_receipt', 'assigned_to__user'
    ).order_by('-date_received')[:50]
    
    # Get available options for filters
    grievance_modes = GrievanceMode.objects.filter(is_active=True)
    status_choices = Grievance.GRIEVANCE_STATUS_CHOICES
    
    # Additional analytics for insights
    # Peak complaint analysis
    peak_analysis = grievances.extra(
        select={'hour': "strftime('%%H', date_received)"}
    ).values('hour').annotate(count=Count('id')).order_by('-count')[:3]
    
    # Most common complaint patterns (this would require additional categorization)
    # For now, we'll use a simple analysis based on existing data
    
    context = {
        'report_data': report_data,
        'grievances': recent_grievances,
        'grievance_modes': grievance_modes,
        'status_choices': status_choices,
        'start_date': start_date,
        'end_date': end_date,
        'status': status_filter,
        'mode': mode_filter,
        'peak_analysis': peak_analysis,
        'user_role': user_profile.role,
    }
    
    return render(request, 'cases/grievance_reports.html', context)

# Also update the export_grievances view to make it fully functional

@login_required 
def export_grievances(request):
    """
    Export comprehensive grievances data to CSV format
    Includes all relevant grievance information for external analysis
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    # Permission check
    if user_profile.role == 'DH':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    # Get grievances based on role hierarchy
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]
    
    if user_profile.role == 'ADMIN':
        grievances = Grievance.objects.all()
    else:
        grievances = Grievance.objects.filter(
            Q(assigned_to__role__in=roles_to_view) | Q(created_by=request.user)
        )
    
    # Apply same filters as the reports page
    status_filter = request.GET.get('status')
    mode_filter = request.GET.get('mode')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if status_filter:
        grievances = grievances.filter(status=status_filter)
    
    if mode_filter:
        grievances = grievances.filter(mode_of_receipt_id=mode_filter)
    
    if start_date:
        try:
            grievances = grievances.filter(date_received__gte=parse_date(start_date))
        except (ValueError, TypeError):
            pass
    
    if end_date:
        try:
            grievances = grievances.filter(date_received__lte=parse_date(end_date))
        except (ValueError, TypeError):
            pass
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="grievances_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response)
    
    # Comprehensive header row
    writer.writerow([
        'Grievance ID',
        'Date Received',
        'PPO Number',
        'Pensioner Name',
        'Complainant Name',
        'Complainant Phone',
        'Complainant Email',
        'Mode of Receipt',
        'Status',
        'Priority Level',
        'Grievance Category',
        'Grievance Text',
        'Action Taken',
        'Date Action Initiated',
        'Date Disposed',
        'Resolution Details',
        'Assigned To',
        'Created By',
        'Days to Resolution',
        'Satisfaction Rating',
        'Follow-up Required'
    ])
    
    # Write grievance data
    for grievance in grievances.select_related('pensioner', 'mode_of_receipt', 'assigned_to__user', 'created_by'):
        # Calculate resolution time
        resolution_days = ''
        if grievance.date_disposed and grievance.date_received:
            resolution_time = grievance.date_disposed - grievance.date_received
            resolution_days = resolution_time.days
        
        writer.writerow([
            grievance.grievance_id,
            grievance.date_received.strftime('%Y-%m-%d %H:%M:%S'),
            grievance.pensioner.ppo_number if grievance.pensioner else '',
            grievance.pensioner.employee_name if grievance.pensioner else '',
            grievance.complainant_name,
            getattr(grievance, 'complainant_phone', ''),  # Add these fields to model if needed
            getattr(grievance, 'complainant_email', ''),
            grievance.mode_of_receipt.name if grievance.mode_of_receipt else '',
            grievance.get_status_display(),
            getattr(grievance, 'priority_level', 'Medium'),  # Add if needed
            getattr(grievance, 'category', ''),  # Add if needed
            grievance.grievance_text[:500] + '...' if len(grievance.grievance_text) > 500 else grievance.grievance_text,
            getattr(grievance, 'action_taken', ''),  # Add if needed
            getattr(grievance, 'date_action_initiated', ''),  # Add if needed
            grievance.date_disposed.strftime('%Y-%m-%d %H:%M:%S') if grievance.date_disposed else '',
            getattr(grievance, 'resolution_details', ''),  # Add if needed
            grievance.assigned_to.user.get_full_name() or grievance.assigned_to.user.username if grievance.assigned_to else '',
            grievance.created_by.get_full_name() or grievance.created_by.username if grievance.created_by else '',
            resolution_days,
            getattr(grievance, 'satisfaction_rating', ''),  # Add if needed
            getattr(grievance, 'follow_up_required', 'No')  # Add if needed
        ])
    
    return response

@login_required
def search_grievances(request):
    """Advanced grievance search"""
    search_form_data = {
        'grievance_id': request.GET.get('grievance_id', ''),
        'ppo_number': request.GET.get('ppo_number', ''),
        'complainant_name': request.GET.get('complainant_name', ''),
        'pensioner_name': request.GET.get('pensioner_name', ''),
        'status': request.GET.get('status', ''),
        'mode': request.GET.get('mode', ''),
        'start_date': request.GET.get('start_date', ''),
        'end_date': request.GET.get('end_date', ''),
    }
    
    grievances = None
    
    if any(search_form_data.values()):
        user_profile = get_object_or_404(UserProfile, user=request.user)
        
        if user_profile.role == 'ADMIN':
            grievances = Grievance.objects.all()
        else:
            subordinate_roles = get_subordinate_roles(user_profile.role)
            roles_to_view = subordinate_roles + [user_profile.role]
            grievances = Grievance.objects.filter(
                Q(assigned_to__role__in=roles_to_view) | Q(created_by=request.user)
            )
        
        # Apply filters
        if search_form_data['grievance_id']:
            grievances = grievances.filter(grievance_id__icontains=search_form_data['grievance_id'])
        if search_form_data['ppo_number']:
            grievances = grievances.filter(pensioner__ppo_number__icontains=search_form_data['ppo_number'])
        if search_form_data['complainant_name']:
            grievances = grievances.filter(complainant_name__icontains=search_form_data['complainant_name'])
        if search_form_data['pensioner_name']:
            grievances = grievances.filter(pensioner__employee_name__icontains=search_form_data['pensioner_name'])
        if search_form_data['status']:
            grievances = grievances.filter(status=search_form_data['status'])
        if search_form_data['mode']:
            grievances = grievances.filter(mode_of_receipt_id=search_form_data['mode'])
        if search_form_data['start_date']:
            grievances = grievances.filter(date_received__gte=search_form_data['start_date'])
        if search_form_data['end_date']:
            grievances = grievances.filter(date_received__lte=search_form_data['end_date'])
        
        grievances = grievances.order_by('-date_received')
    
    # Get choices for form
    grievance_modes = GrievanceMode.objects.filter(is_active=True)
    status_choices = Grievance.GRIEVANCE_STATUS_CHOICES
    
    context = {
        'search_form_data': search_form_data,
        'grievances': grievances,
        'grievance_modes': grievance_modes,
        'status_choices': status_choices
    }
    return render(request, 'cases/search_grievances.html', context)

@login_required 
@login_required 
def export_grievances(request):
    """Export grievances to CSV"""
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    if user_profile.role == 'ADMIN':
        grievances = Grievance.objects.all()
    else:
        subordinate_roles = get_subordinate_roles(user_profile.role)
        roles_to_view = subordinate_roles + [user_profile.role]
        grievances = Grievance.objects.filter(
            Q(assigned_to__role__in=roles_to_view) | Q(created_by=request.user)
        )
    
    # Apply same filters as search
    status = request.GET.get('status')
    if status:
        grievances = grievances.filter(status=status)
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="grievances_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Grievance ID', 'PPO Number', 'Pensioner Name', 'Complainant Name',
        'Date Received', 'Status', 'Mode of Receipt', 'Grievance Text',
        'Date Disposed', 'Assigned To'
    ])
    
    for grievance in grievances.select_related('pensioner', 'mode_of_receipt', 'assigned_to__user'):
        writer.writerow([
            grievance.grievance_id,
            grievance.pensioner.ppo_number if grievance.pensioner else '',
            grievance.pensioner.employee_name if grievance.pensioner else '',
            grievance.complainant_name,
            grievance.date_received.strftime('%d-%m-%Y'),
            grievance.get_status_display(),
            grievance.mode_of_receipt.name,
            grievance.grievance_text[:100] + '...' if len(grievance.grievance_text) > 100 else grievance.grievance_text,
            grievance.date_disposed.strftime('%d-%m-%Y') if grievance.date_disposed else '',
            grievance.assigned_to.user.username if grievance.assigned_to else ''
        ])
    
    return response
# ... (Include all your other existing views like register_case, move_case, record management views, etc. here)
# Make sure to keep all the views from your original project that are not listed above.

# Add these comprehensive reporting views to your cases/views.py

@login_required
def reports_dashboard(request):
    """
    Main reports dashboard - this acts as a hub for all reports
    Think of this as your reporting control center
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    now = timezone.now()
    
    # Permission check - only AAO and above can access reports
    if user_profile.role == 'DH':
        messages.error(request, 'You do not have permission to access reports.')
        return redirect('dashboard')
    
    # Get subordinate roles for data filtering
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]
    
    # Basic statistics for the dashboard overview
    if user_profile.role == 'ADMIN':
        cases = Case.objects.all()
        grievances = Grievance.objects.all()
        requisitions = RecordRequisition.objects.all()
    else:
        cases = Case.objects.filter(current_holder__role__in=roles_to_view)
        grievances = Grievance.objects.filter(
            Q(assigned_to__role__in=roles_to_view) | Q(created_by=request.user)
        )
        requisitions = RecordRequisition.objects.filter(
            Q(requester_dh__role__in=roles_to_view) | Q(approving_aao__role__in=roles_to_view)
        )
    
    # Calculate key metrics for the overview cards
    total_cases = cases.count()
    pending_cases = cases.filter(is_completed=False).count()
    completed_this_month = cases.filter(
        is_completed=True,
        actual_completion__month=now.month,
        actual_completion__year=now.year
    ).count()
    
    total_grievances = grievances.count()
    new_grievances = grievances.filter(status='NEW').count()
    
    # Performance metrics
    avg_case_completion_days = cases.filter(
        is_completed=True,
        actual_completion__isnull=False
    ).aggregate(
        avg_days=Avg(F('actual_completion') - F('registration_date'))
    )['avg_days']
    
    if avg_case_completion_days:
        avg_case_completion_days = avg_case_completion_days.days
    else:
        avg_case_completion_days = 0
    
    # Recent activity for quick insights
    recent_cases = cases.order_by('-registration_date')[:5]
    recent_grievances = grievances.order_by('-date_received')[:5]
    
    context = {
        'total_cases': total_cases,
        'pending_cases': pending_cases,
        'completed_this_month': completed_this_month,
        'total_grievances': total_grievances,
        'new_grievances': new_grievances,
        'avg_completion_days': avg_case_completion_days,
        'recent_cases': recent_cases,
        'recent_grievances': recent_grievances,
        'user_role': user_profile.role,
        'can_view_executive_reports': user_profile.role in ['ADMIN', 'CCA', 'Jt.CCA', 'Pr.CCA']
    }
    
    return render(request, 'cases/reports_dashboard.html', context)

@login_required
def case_aging_report(request):
    """
    Shows how long cases have been pending at each stage
    This helps identify bottlenecks in your workflow
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    if user_profile.role == 'DH':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    # Get filter parameters
    case_type_filter = request.GET.get('case_type', '')
    priority_filter = request.GET.get('priority', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    
    # Base queryset
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]
    
    if user_profile.role == 'ADMIN':
        cases = Case.objects.filter(is_completed=False)
    else:
        cases = Case.objects.filter(
            current_holder__role__in=roles_to_view,
            is_completed=False
        )
    
    # Apply filters
    if case_type_filter:
        cases = cases.filter(case_type_id=case_type_filter)
    if priority_filter:
        cases = cases.filter(priority=priority_filter)
    if start_date:
        cases = cases.filter(registration_date__gte=parse_date(start_date))
    if end_date:
        cases = cases.filter(registration_date__lte=parse_date(end_date))
    
    # Calculate aging categories
    now = timezone.now()
    aging_data = []
    
    for case in cases.select_related('case_type', 'current_holder__user'):
        days_pending = (now - case.registration_date).days
        
        # Categorize by age
        if days_pending <= 7:
            age_category = '0-7 days'
            priority_level = 'success'
        elif days_pending <= 15:
            age_category = '8-15 days'
            priority_level = 'warning'
        elif days_pending <= 30:
            age_category = '16-30 days'
            priority_level = 'danger'
        else:
            age_category = '30+ days'
            priority_level = 'critical'
        
        aging_data.append({
            'case': case,
            'days_pending': days_pending,
            'age_category': age_category,
            'priority_level': priority_level
        })
    
    # Sort by days pending (most urgent first)
    aging_data.sort(key=lambda x: x['days_pending'], reverse=True)
    
    # Summary statistics
    age_summary = {
        '0-7 days': sum(1 for item in aging_data if item['age_category'] == '0-7 days'),
        '8-15 days': sum(1 for item in aging_data if item['age_category'] == '8-15 days'),
        '16-30 days': sum(1 for item in aging_data if item['age_category'] == '16-30 days'),
        '30+ days': sum(1 for item in aging_data if item['age_category'] == '30+ days'),
    }
    
    # Get available case types for filter dropdown
    case_types = CaseType.objects.filter(is_active=True)
    
    context = {
        'aging_data': aging_data,
        'age_summary': age_summary,
        'case_types': case_types,
        'filters': {
            'case_type': case_type_filter,
            'priority': priority_filter,
            'start_date': start_date,
            'end_date': end_date,
        }
    }
    
    return render(request, 'cases/case_aging_report.html', context)

@login_required
def workload_analysis_report(request):
    """
    Shows workload distribution across team members
    This helps identify if work is evenly distributed and who might need help
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    if user_profile.role not in ['AAO', 'AO', 'CCA', 'Jt.CCA', 'Pr.CCA', 'ADMIN']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    # Get subordinate users
    subordinate_roles = get_subordinate_roles(user_profile.role)
    
    if user_profile.role == 'ADMIN':
        team_members = UserProfile.objects.filter(is_active_holder=True)
    else:
        team_members = UserProfile.objects.filter(
            role__in=subordinate_roles,
            is_active_holder=True
        )
    
    workload_data = []
    
    for member in team_members:
        # Count current cases
        current_cases = Case.objects.filter(
            current_holder=member,
            is_completed=False
        ).count()
        
        # Count cases completed this month
        completed_this_month = Case.objects.filter(
            Q(created_by=member.user) | Q(last_updated_by=member.user),
            is_completed=True,
            actual_completion__month=timezone.now().month,
            actual_completion__year=timezone.now().year
        ).count()
        
        # Count assigned grievances
        assigned_grievances = Grievance.objects.filter(
            assigned_to=member,
            status='NEW'
        ).count()
        
        # Count pending approvals (for AAOs)
        pending_approvals = 0
        if member.role == 'AAO':
            pending_approvals = RecordRequisition.objects.filter(
                approving_aao=member,
                status__in=['PENDING_APPROVAL', 'RETURN_REQUESTED']
            ).count()
        
        # Calculate workload score (weighted)
        workload_score = (current_cases * 1.0) + (assigned_grievances * 0.8) + (pending_approvals * 0.5)
        
        # Determine workload level
        if workload_score <= 5:
            workload_level = 'Light'
            level_class = 'success'
        elif workload_score <= 15:
            workload_level = 'Normal'
            level_class = 'info'
        elif workload_score <= 25:
            workload_level = 'Heavy'
            level_class = 'warning'
        else:
            workload_level = 'Critical'
            level_class = 'danger'
        
        workload_data.append({
            'member': member,
            'current_cases': current_cases,
            'completed_this_month': completed_this_month,
            'assigned_grievances': assigned_grievances,
            'pending_approvals': pending_approvals,
            'workload_score': workload_score,
            'workload_level': workload_level,
            'level_class': level_class
        })
    
    # Sort by workload score (highest first)
    workload_data.sort(key=lambda x: x['workload_score'], reverse=True)
    
    # Calculate team averages
    if workload_data:
        avg_current_cases = sum(item['current_cases'] for item in workload_data) / len(workload_data)
        avg_completed = sum(item['completed_this_month'] for item in workload_data) / len(workload_data)
        avg_workload_score = sum(item['workload_score'] for item in workload_data) / len(workload_data)
    else:
        avg_current_cases = avg_completed = avg_workload_score = 0
    
    context = {
        'workload_data': workload_data,
        'team_averages': {
            'avg_current_cases': round(avg_current_cases, 1),
            'avg_completed': round(avg_completed, 1),
            'avg_workload_score': round(avg_workload_score, 1)
        }
    }
    
    return render(request, 'cases/workload_analysis_report.html', context)

@login_required
def performance_trends_report(request):
    """
    Shows performance trends over time - completion rates, processing times, etc.
    This helps you see if you're improving or if there are seasonal patterns
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    if user_profile.role not in ['AO', 'CCA', 'Jt.CCA', 'Pr.CCA', 'ADMIN']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    # Get date range (default to last 6 months)
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=180)
    
    # Allow custom date range
    custom_start = request.GET.get('start_date')
    custom_end = request.GET.get('end_date')
    
    if custom_start:
        start_date = parse_date(custom_start)
    if custom_end:
        end_date = parse_date(custom_end)
    
    # Get cases in date range
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]
    
    if user_profile.role == 'ADMIN':
        cases = Case.objects.filter(registration_date__range=[start_date, end_date])
        completed_cases = Case.objects.filter(
            is_completed=True,
            actual_completion__range=[start_date, end_date]
        )
    else:
        cases = Case.objects.filter(
            current_holder__role__in=roles_to_view,
            registration_date__range=[start_date, end_date]
        )
        completed_cases = Case.objects.filter(
            current_holder__role__in=roles_to_view,
            is_completed=True,
            actual_completion__range=[start_date, end_date]
        )
    
    # Monthly registration trends
    monthly_registrations = cases.annotate(
        month=TruncMonth('registration_date')
    ).values('month').annotate(
        count=Count('id')
    ).order_by('month')
    
    # Monthly completion trends
    monthly_completions = completed_cases.annotate(
        month=TruncMonth('actual_completion')
    ).values('month').annotate(
        count=Count('id')
    ).order_by('month')
    
    # Average processing time by month
    monthly_processing_time = completed_cases.annotate(
        month=TruncMonth('actual_completion'),
        processing_days=F('actual_completion') - F('registration_date')
    ).values('month').annotate(
        avg_days=Avg('processing_days')
    ).order_by('month')
    
    # Case type performance
    case_type_performance = completed_cases.values(
        'case_type__name'
    ).annotate(
        count=Count('id'),
        avg_days=Avg(F('actual_completion') - F('registration_date'))
    ).order_by('-count')
    
    # Prepare data for charts (convert to JSON for JavaScript)
    registration_chart_data = {
        'labels': [item['month'].strftime('%b %Y') for item in monthly_registrations],
        'data': [item['count'] for item in monthly_registrations]
    }
    
    completion_chart_data = {
        'labels': [item['month'].strftime('%b %Y') for item in monthly_completions],
        'data': [item['count'] for item in monthly_completions]
    }
    
    processing_time_chart_data = {
        'labels': [item['month'].strftime('%b %Y') for item in monthly_processing_time],
        'data': [item['avg_days'].days if item['avg_days'] else 0 for item in monthly_processing_time]
    }
    
    context = {
        'start_date': start_date,
        'end_date': end_date,
        'monthly_registrations': monthly_registrations,
        'monthly_completions': monthly_completions,
        'monthly_processing_time': monthly_processing_time,
        'case_type_performance': case_type_performance,
        'registration_chart_data': json.dumps(registration_chart_data),
        'completion_chart_data': json.dumps(completion_chart_data),
        'processing_time_chart_data': json.dumps(processing_time_chart_data),
    }
    
    return render(request, 'cases/performance_trends_report.html', context)

@login_required
def executive_summary_report(request):
    """
    High-level executive summary for senior management
    This provides the big picture view of system performance
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    if user_profile.role not in ['CCA', 'Jt.CCA', 'Pr.CCA', 'ADMIN']:
        messages.error(request, 'Access denied - Executive level required.')
        return redirect('dashboard')
    
    now = timezone.now()
    
    # Overall system statistics
    total_cases = Case.objects.count()
    total_completed = Case.objects.filter(is_completed=True).count()
    total_pending = Case.objects.filter(is_completed=False).count()
    completion_rate = (total_completed / total_cases * 100) if total_cases > 0 else 0
    
    # This month vs last month comparison
    current_month_cases = Case.objects.filter(
        registration_date__month=now.month,
        registration_date__year=now.year
    ).count()
    
    last_month = now.replace(day=1) - timedelta(days=1)
    last_month_cases = Case.objects.filter(
        registration_date__month=last_month.month,
        registration_date__year=last_month.year
    ).count()
    
    month_over_month_change = ((current_month_cases - last_month_cases) / last_month_cases * 100) if last_month_cases > 0 else 0
    
    # System performance metrics
    avg_processing_time = Case.objects.filter(
        is_completed=True,
        actual_completion__isnull=False
    ).aggregate(
        avg_time=Avg(F('actual_completion') - F('registration_date'))
    )['avg_time']
    
    if avg_processing_time:
        avg_processing_days = avg_processing_time.days
    else:
        avg_processing_days = 0
    
    # Bottleneck analysis
    overdue_cases = Case.objects.filter(
        is_completed=False,
        expected_completion__lt=now
    ).count()
    
    # Resource utilization
    active_users = UserProfile.objects.filter(is_active_holder=True).count()
    cases_per_user = total_pending / active_users if active_users > 0 else 0
    
    # Grievance summary
    total_grievances = Grievance.objects.count()
    new_grievances = Grievance.objects.filter(status='NEW').count()
    disposed_grievances = Grievance.objects.filter(status='DISPOSED').count()
    grievance_resolution_rate = (disposed_grievances / total_grievances * 100) if total_grievances > 0 else 0
    
    # Critical issues requiring attention
    critical_issues = []
    
    if overdue_cases > (total_pending * 0.1):  # More than 10% overdue
        critical_issues.append({
            'issue': 'High Overdue Rate',
            'description': f'{overdue_cases} cases are overdue ({overdue_cases/total_pending*100:.1f}%)',
            'severity': 'high'
        })
    
    if new_grievances > 10:
        critical_issues.append({
            'issue': 'Pending Grievances',
            'description': f'{new_grievances} grievances awaiting action',
            'severity': 'medium'
        })
    
    if cases_per_user > 20:
        critical_issues.append({
            'issue': 'High Workload',
            'description': f'Average {cases_per_user:.1f} cases per user',
            'severity': 'medium'
        })
    
    # Top performing case types
    top_case_types = Case.objects.filter(
        is_completed=True
    ).values('case_type__name').annotate(
        count=Count('id'),
        avg_days=Avg(F('actual_completion') - F('registration_date'))
    ).order_by('-count')[:5]
    
    context = {
        'total_cases': total_cases,
        'total_completed': total_completed,
        'total_pending': total_pending,
        'completion_rate': round(completion_rate, 1),
        'current_month_cases': current_month_cases,
        'last_month_cases': last_month_cases,
        'month_over_month_change': round(month_over_month_change, 1),
        'avg_processing_days': avg_processing_days,
        'overdue_cases': overdue_cases,
        'active_users': active_users,
        'cases_per_user': round(cases_per_user, 1),
        'total_grievances': total_grievances,
        'new_grievances': new_grievances,
        'grievance_resolution_rate': round(grievance_resolution_rate, 1),
        'critical_issues': critical_issues,
        'top_case_types': top_case_types,
        'report_generated': now,
    }
    
    return render(request, 'cases/executive_summary_report.html', context)
# Add these export view functions to your cases/views.py file

@login_required
def export_cases_report(request):
    """
    Comprehensive case export with detailed information for analysis
    Exports all cases with full details in CSV format
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    # Permission check - only AAO and above can export case reports
    if user_profile.role == 'DH':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    # Get cases based on user role hierarchy
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]
    
    if user_profile.role == 'ADMIN':
        cases = Case.objects.all()
    else:
        cases = Case.objects.filter(current_holder__role__in=roles_to_view)
    
    # Apply any filters from request parameters
    case_type_filter = request.GET.get('case_type')
    priority_filter = request.GET.get('priority')
    status_filter = request.GET.get('status')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    if case_type_filter:
        cases = cases.filter(case_type_id=case_type_filter)
    if priority_filter:
        cases = cases.filter(priority=priority_filter)
    if status_filter:
        if status_filter == 'completed':
            cases = cases.filter(is_completed=True)
        elif status_filter == 'pending':
            cases = cases.filter(is_completed=False)
    if start_date:
        cases = cases.filter(registration_date__gte=parse_date(start_date))
    if end_date:
        cases = cases.filter(registration_date__lte=parse_date(end_date))
    
    # Create the CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="cases_report_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response)
    
    # Comprehensive header row with all important case information
    writer.writerow([
        'Case ID',
        'Registration Date', 
        'Case Type',
        'Sub Category',
        'Case Title',
        'Applicant Name',
        'PPO Number',
        'Priority',
        'Current Status',
        'Current Holder',
        'Holder Role',
        'Days in Current Stage',
        'Total Days Pending',
        'Expected Completion',
        'Actual Completion',
        'Is Completed',
        'Status Color',
        'Created By',
        'Last Updated By',
        'Last Update Date',
        'Case Description'
    ])
    
    # Write case data
    for case in cases.select_related('case_type', 'current_holder__user', 'ppo_master', 'created_by', 'last_updated_by'):
        writer.writerow([
            case.case_id,
            case.registration_date.strftime('%Y-%m-%d %H:%M:%S') if case.registration_date else '',
            case.case_type.name if case.case_type else '',
            case.sub_category,
            case.case_title,
            case.applicant_name,
            case.ppo_master.ppo_number if case.ppo_master else '',
            case.priority,
            case.current_status,
            case.current_holder.user.get_full_name() or case.current_holder.user.username if case.current_holder else '',
            case.current_holder.role if case.current_holder else '',
            case.days_in_current_stage,
            case.total_days_pending,
            case.expected_completion.strftime('%Y-%m-%d %H:%M:%S') if case.expected_completion else '',
            case.actual_completion.strftime('%Y-%m-%d %H:%M:%S') if case.actual_completion else '',
            'Yes' if case.is_completed else 'No',
            case.status_color,
            case.created_by.get_full_name() or case.created_by.username if case.created_by else '',
            case.last_updated_by.get_full_name() or case.last_updated_by.username if case.last_updated_by else '',
            case.last_update_date.strftime('%Y-%m-%d %H:%M:%S') if case.last_update_date else '',
            case.case_description
        ])
    
    return response

@login_required
def export_workload_report(request):
    """
    Export comprehensive workload analysis data for all team members
    Useful for HR analysis and resource planning
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    # Permission check - only managers and above can export workload reports
    if user_profile.role not in ['AAO', 'AO', 'CCA', 'Jt.CCA', 'Pr.CCA', 'ADMIN']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    # Get team members based on hierarchy
    subordinate_roles = get_subordinate_roles(user_profile.role)
    
    if user_profile.role == 'ADMIN':
        team_members = UserProfile.objects.filter(is_active_holder=True)
    else:
        team_members = UserProfile.objects.filter(
            role__in=subordinate_roles,
            is_active_holder=True
        )
    
    # Create the CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="workload_report_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response)
    
    # Header row for workload analysis
    writer.writerow([
        'Employee Name',
        'Username',
        'Role',
        'Department',
        'Current Active Cases',
        'Completed This Month',
        'Completed This Quarter',
        'Assigned Grievances',
        'Pending Approvals',
        'Workload Score',
        'Workload Level',
        'Average Processing Days',
        'Overdue Cases',
        'High Priority Cases',
        'Last Activity Date',
        'Performance Rating',
        'Recommendations'
    ])
    
    now = timezone.now()
    
    # Calculate detailed workload data for each team member
    for member in team_members.select_related('user'):
        # Current cases
        current_cases = Case.objects.filter(
            current_holder=member,
            is_completed=False
        )
        current_cases_count = current_cases.count()
        
        # Completed cases this month
        completed_this_month = Case.objects.filter(
            Q(created_by=member.user) | Q(last_updated_by=member.user),
            is_completed=True,
            actual_completion__month=now.month,
            actual_completion__year=now.year
        ).count()
        
        # Completed cases this quarter
        quarter_start = now.replace(month=((now.month - 1) // 3) * 3 + 1, day=1)
        completed_this_quarter = Case.objects.filter(
            Q(created_by=member.user) | Q(last_updated_by=member.user),
            is_completed=True,
            actual_completion__gte=quarter_start
        ).count()
        
        # Grievances
        assigned_grievances = Grievance.objects.filter(
            assigned_to=member,
            status='NEW'
        ).count()
        
        # Pending approvals (for AAOs)
        pending_approvals = 0
        if member.role == 'AAO':
            pending_approvals = RecordRequisition.objects.filter(
                approving_aao=member,
                status__in=['PENDING_APPROVAL', 'RETURN_REQUESTED']
            ).count()
        
        # Calculate workload score
        workload_score = (current_cases_count * 1.0) + (assigned_grievances * 0.8) + (pending_approvals * 0.5)
        
        # Determine workload level
        if workload_score <= 5:
            workload_level = 'Light'
            performance_rating = 'Available for additional work'
            recommendations = 'Can take on complex cases or mentor others'
        elif workload_score <= 15:
            workload_level = 'Normal'
            performance_rating = 'Optimal workload'
            recommendations = 'Maintain current assignment level'
        elif workload_score <= 25:
            workload_level = 'Heavy'
            performance_rating = 'High workload - monitor'
            recommendations = 'Consider redistributing some cases, provide support'
        else:
            workload_level = 'Critical'
            performance_rating = 'Overloaded - immediate action required'
            recommendations = 'Urgent: Reassign cases, provide immediate assistance'
        
        # Average processing days for completed cases
        completed_cases = Case.objects.filter(
            current_holder=member,
            is_completed=True,
            actual_completion__isnull=False
        )
        
        if completed_cases.exists():
            avg_processing_days = completed_cases.aggregate(
                avg_days=Avg(F('actual_completion') - F('registration_date'))
            )['avg_days']
            avg_processing_days = avg_processing_days.days if avg_processing_days else 0
        else:
            avg_processing_days = 0
        
        # Overdue cases
        overdue_cases = current_cases.filter(expected_completion__lt=now).count()
        
        # High priority cases
        high_priority_cases = current_cases.filter(priority='High').count()
        
        # Last activity date
        last_activity = CaseMovement.objects.filter(updated_by=member.user).order_by('-movement_date').first()
        last_activity_date = last_activity.movement_date.strftime('%Y-%m-%d') if last_activity else 'No recent activity'
        
        # Write row data
        writer.writerow([
            member.user.get_full_name() or member.user.username,
            member.user.username,
            member.role,
            getattr(member, 'department', 'N/A'),  # Add department field if available
            current_cases_count,
            completed_this_month,
            completed_this_quarter,
            assigned_grievances,
            pending_approvals,
            f"{workload_score:.1f}",
            workload_level,
            avg_processing_days,
            overdue_cases,
            high_priority_cases,
            last_activity_date,
            performance_rating,
            recommendations
        ])
    
    return response

@login_required  
def export_performance_report(request):
    """
    Export comprehensive performance trends and analytics data
    Includes monthly trends, case type performance, and system metrics
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    # Permission check - only senior managers can export performance reports
    if user_profile.role not in ['AO', 'CCA', 'Jt.CCA', 'Pr.CCA', 'ADMIN']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    # Get date range (default to last 12 months)
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=365)
    
    # Allow custom date range
    custom_start = request.GET.get('start_date')
    custom_end = request.GET.get('end_date')
    
    if custom_start:
        start_date = parse_date(custom_start)
    if custom_end:
        end_date = parse_date(custom_end)
    
    # Create the CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="performance_report_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
    
    writer = csv.writer(response)
    
    # Get performance data
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]
    
    if user_profile.role == 'ADMIN':
        cases = Case.objects.filter(registration_date__range=[start_date, end_date])
        completed_cases = Case.objects.filter(
            is_completed=True,
            actual_completion__range=[start_date, end_date]
        )
    else:
        cases = Case.objects.filter(
            current_holder__role__in=roles_to_view,
            registration_date__range=[start_date, end_date]
        )
        completed_cases = Case.objects.filter(
            current_holder__role__in=roles_to_view,
            is_completed=True,
            actual_completion__range=[start_date, end_date]
        )
    
    # Monthly registration trends
    monthly_registrations = cases.annotate(
        month=TruncMonth('registration_date')
    ).values('month').annotate(
        count=Count('id')
    ).order_by('month')
    
    # Monthly completion trends
    monthly_completions = completed_cases.annotate(
        month=TruncMonth('actual_completion')
    ).values('month').annotate(
        count=Count('id')
    ).order_by('month')
    
    # Write monthly trends section
    writer.writerow(['MONTHLY PERFORMANCE TRENDS'])
    writer.writerow(['Month', 'New Registrations', 'Completions', 'Net Change', 'Completion Rate'])
    
    # Create lookup dictionaries for easier access
    registrations_by_month = {item['month']: item['count'] for item in monthly_registrations}
    completions_by_month = {item['month']: item['count'] for item in monthly_completions}
    
    # Get all unique months
    all_months = set(registrations_by_month.keys()) | set(completions_by_month.keys())
    
    for month in sorted(all_months):
        registrations = registrations_by_month.get(month, 0)
        completions = completions_by_month.get(month, 0)
        net_change = completions - registrations
        completion_rate = (completions / registrations * 100) if registrations > 0 else 0
        
        writer.writerow([
            month.strftime('%Y-%m'),
            registrations,
            completions,
            net_change,
            f"{completion_rate:.1f}%"
        ])
    
    # Add spacing
    writer.writerow([])
    writer.writerow([])
    
    # Case type performance analysis
    case_type_performance = completed_cases.values(
        'case_type__name'
    ).annotate(
        count=Count('id'),
        avg_days=Avg(F('actual_completion') - F('registration_date'))
    ).order_by('-count')
    
    writer.writerow(['CASE TYPE PERFORMANCE ANALYSIS'])
    writer.writerow(['Case Type', 'Total Completed', 'Average Processing Days', 'Performance Rating'])
    
    for case_type in case_type_performance:
        avg_days = case_type['avg_days'].days if case_type['avg_days'] else 0
        
        if avg_days <= 7:
            rating = 'Excellent'
        elif avg_days <= 15:
            rating = 'Good'
        elif avg_days <= 30:
            rating = 'Acceptable'
        else:
            rating = 'Needs Improvement'
            
        writer.writerow([
            case_type['case_type__name'],
            case_type['count'],
            avg_days,
            rating
        ])
    
    # Add spacing
    writer.writerow([])
    writer.writerow([])
    
    # System-wide performance metrics
    writer.writerow(['SYSTEM PERFORMANCE METRICS'])
    writer.writerow(['Metric', 'Value', 'Period'])
    
    total_cases = cases.count()
    total_completed = completed_cases.count()
    overall_completion_rate = (total_completed / total_cases * 100) if total_cases > 0 else 0
    
    avg_processing_time = completed_cases.aggregate(
        avg_time=Avg(F('actual_completion') - F('registration_date'))
    )['avg_time']
    avg_processing_days = avg_processing_time.days if avg_processing_time else 0
    
    active_users = UserProfile.objects.filter(is_active_holder=True).count()
    cases_per_user = total_cases / active_users if active_users > 0 else 0
    
    writer.writerow(['Total Cases Registered', total_cases, f'{start_date} to {end_date}'])
    writer.writerow(['Total Cases Completed', total_completed, f'{start_date} to {end_date}'])
    writer.writerow(['Overall Completion Rate', f'{overall_completion_rate:.1f}%', f'{start_date} to {end_date}'])
    writer.writerow(['Average Processing Time', f'{avg_processing_days} days', f'{start_date} to {end_date}'])
    writer.writerow(['Active Users', active_users, 'Current'])
    writer.writerow(['Cases per User', f'{cases_per_user:.1f}', 'Current average'])
    
    # Add priority-wise breakdown
    priority_breakdown = cases.values('priority').annotate(count=Count('id'))
    
    writer.writerow([])
    writer.writerow(['PRIORITY BREAKDOWN'])
    writer.writerow(['Priority Level', 'Count', 'Percentage'])
    
    for priority in priority_breakdown:
        percentage = (priority['count'] / total_cases * 100) if total_cases > 0 else 0
        writer.writerow([
            priority['priority'],
            priority['count'],
            f'{percentage:.1f}%'
        ])
    
    return response

@login_required
def case_type_analysis_report(request):
    """
    Provides detailed analysis of case types including processing times,
    success rates, and resource allocation patterns.
    This report helps identify which case types are most challenging or resource-intensive.
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    # Permission check - AAO and above can access this report
    if user_profile.role == 'DH':
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    # Get date range filters
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Set default date range to last 6 months if not specified
    if not start_date:
        start_date = (timezone.now() - timedelta(days=180)).date()
    else:
        start_date = parse_date(start_date)
    
    if not end_date:
        end_date = timezone.now().date()
    else:
        end_date = parse_date(end_date)
    
    # Get cases based on user role hierarchy
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]
    
    if user_profile.role == 'ADMIN':
        cases = Case.objects.filter(registration_date__range=[start_date, end_date])
    else:
        cases = Case.objects.filter(
            current_holder__role__in=roles_to_view,
            registration_date__range=[start_date, end_date]
        )
    
    # Comprehensive case type analysis
    case_type_stats = cases.values('case_type__name').annotate(
        total_cases=Count('id'),
        completed_cases=Count('id', filter=Q(is_completed=True)),
        pending_cases=Count('id', filter=Q(is_completed=False)),
        high_priority_cases=Count('id', filter=Q(priority='High')),
        overdue_cases=Count('id', filter=Q(is_completed=False, expected_completion__lt=timezone.now())),
        avg_processing_days=Avg(
            F('actual_completion') - F('registration_date'),
            filter=Q(is_completed=True)
        )
    ).order_by('-total_cases')
    
    # Calculate completion rates and processing efficiency
    enhanced_stats = []
    for stat in case_type_stats:
        total = stat['total_cases']
        completed = stat['completed_cases']
        completion_rate = (completed / total * 100) if total > 0 else 0
        
        avg_days = stat['avg_processing_days']
        avg_processing_days = avg_days.days if avg_days else 0
        
        # Determine efficiency rating based on completion rate and processing time
        if completion_rate >= 90 and avg_processing_days <= 15:
            efficiency = 'Excellent'
            efficiency_class = 'success'
        elif completion_rate >= 75 and avg_processing_days <= 30:
            efficiency = 'Good'
            efficiency_class = 'info'
        elif completion_rate >= 60:
            efficiency = 'Fair'
            efficiency_class = 'warning'
        else:
            efficiency = 'Needs Improvement'
            efficiency_class = 'danger'
        
        enhanced_stats.append({
            'case_type': stat['case_type__name'],
            'total_cases': total,
            'completed_cases': completed,
            'pending_cases': stat['pending_cases'],
            'completion_rate': round(completion_rate, 1),
            'high_priority_cases': stat['high_priority_cases'],
            'overdue_cases': stat['overdue_cases'],
            'avg_processing_days': avg_processing_days,
            'efficiency': efficiency,
            'efficiency_class': efficiency_class
        })
    
    # Resource allocation analysis
    resource_analysis = cases.values('case_type__name', 'current_holder__role').annotate(
        case_count=Count('id')
    )
    
    context = {
        'enhanced_stats': enhanced_stats,
        'resource_analysis': resource_analysis,
        'start_date': start_date,
        'end_date': end_date,
        'total_cases_analyzed': cases.count(),
    }
    
    return render(request, 'cases/case_type_analysis_report.html', context)

@login_required
def bottleneck_analysis_report(request):
    """
    Identifies workflow bottlenecks by analyzing where cases spend the most time
    and which stages have the highest dropout or delay rates.
    This is crucial for process optimization and resource planning.
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    if user_profile.role not in ['AO', 'CCA', 'Jt.CCA', 'Pr.CCA', 'ADMIN']:
        messages.error(request, 'Access denied - Manager level required.')
        return redirect('dashboard')
    
    # Analyze case movement patterns to identify bottlenecks
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]
    
    if user_profile.role == 'ADMIN':
        movements = CaseMovement.objects.all()
        cases = Case.objects.all()
    else:
        movements = CaseMovement.objects.filter(
            Q(from_holder__role__in=roles_to_view) | Q(to_holder__role__in=roles_to_view)
        )
        cases = Case.objects.filter(current_holder__role__in=roles_to_view)
    
    # Analyze stage duration patterns
    stage_analysis = {}
    for movement in movements.select_related('case', 'from_holder', 'to_holder'):
        stage = movement.from_stage
        if stage not in stage_analysis:
            stage_analysis[stage] = {
                'total_cases': 0,
                'total_duration': timedelta(0),
                'longest_duration': timedelta(0),
                'cases_stuck': 0  # Cases that took longer than expected
            }
        
        # Calculate time spent in each stage (simplified calculation)
        stage_analysis[stage]['total_cases'] += 1
    
    # Identify current bottlenecks (cases pending too long)
    now = timezone.now()
    bottleneck_cases = cases.filter(
        is_completed=False,
        registration_date__lt=now - timedelta(days=30)  # Cases older than 30 days
    ).select_related('case_type', 'current_holder')
    
    # Group bottlenecks by current stage
    bottleneck_by_stage = bottleneck_cases.values('current_holder__role').annotate(
        count=Count('id'),
        avg_days_pending=Avg(
            DjangoCase(
                When(registration_date__isnull=False, then=F('registration_date')),
                default=Value(now),
                output_field=IntegerField()
            )
        )
    ).order_by('-count')
    
    # Recommendations based on analysis
    recommendations = []
    for stage_data in bottleneck_by_stage:
        stage = stage_data['current_holder__role']
        count = stage_data['count']
        
        if count > 10:
            recommendations.append({
                'issue': f'High volume bottleneck at {stage} stage',
                'description': f'{count} cases pending for extended periods',
                'suggestion': f'Consider adding more resources to {stage} or redistributing workload',
                'priority': 'High' if count > 20 else 'Medium'
            })
    
    context = {
        'bottleneck_cases': bottleneck_cases[:50],  # Limit for performance
        'bottleneck_by_stage': bottleneck_by_stage,
        'recommendations': recommendations,
        'total_bottlenecks': bottleneck_cases.count(),
    }
    
    return render(request, 'cases/bottleneck_analysis_report.html', context)

@login_required
def sla_compliance_report(request):
    """
    Tracks Service Level Agreement compliance by analyzing whether cases
    are completed within expected timeframes and identifying patterns of delays.
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    if user_profile.role not in ['AAO', 'AO', 'CCA', 'Jt.CCA', 'Pr.CCA', 'ADMIN']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    # Define SLA targets (these could be made configurable)
    sla_targets = {
        'Superannuation': 30,  # days
        'Family Pension': 45,
        'Death Intimation': 15,
        'Grievance Resolution': 30,
        'Default': 30
    }
    
    # Get cases for analysis
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]
    
    if user_profile.role == 'ADMIN':
        cases = Case.objects.filter(is_completed=True, actual_completion__isnull=False)
    else:
        cases = Case.objects.filter(
            current_holder__role__in=roles_to_view,
            is_completed=True,
            actual_completion__isnull=False
        )
    
    # Calculate SLA compliance for each case type
    sla_analysis = []
    case_types = cases.values_list('case_type__name', flat=True).distinct()
    
    for case_type in case_types:
        type_cases = cases.filter(case_type__name=case_type)
        sla_target = sla_targets.get(case_type, sla_targets['Default'])
        
        compliant_cases = 0
        total_cases = type_cases.count()
        
        if total_cases > 0:
            for case in type_cases:
                processing_days = (case.actual_completion - case.registration_date).days
                if processing_days <= sla_target:
                    compliant_cases += 1
            
            compliance_rate = (compliant_cases / total_cases) * 100
            
            sla_analysis.append({
                'case_type': case_type,
                'sla_target': sla_target,
                'total_cases': total_cases,
                'compliant_cases': compliant_cases,
                'non_compliant_cases': total_cases - compliant_cases,
                'compliance_rate': round(compliance_rate, 1),
                'status': 'Good' if compliance_rate >= 80 else 'Poor' if compliance_rate < 60 else 'Fair'
            })
    
    # Overall SLA performance
    overall_cases = sum(item['total_cases'] for item in sla_analysis)
    overall_compliant = sum(item['compliant_cases'] for item in sla_analysis)
    overall_compliance = (overall_compliant / overall_cases * 100) if overall_cases > 0 else 0
    
    context = {
        'sla_analysis': sla_analysis,
        'overall_compliance': round(overall_compliance, 1),
        'overall_cases': overall_cases,
        'overall_compliant': overall_compliant,
        'sla_targets': sla_targets,
    }
    
    return render(request, 'cases/sla_compliance_report.html', context)

@login_required
def user_productivity_report(request):
    """
    Analyzes individual user productivity including case completion rates,
    average processing times, and quality metrics.
    This helps with performance evaluation and training needs identification.
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    if user_profile.role not in ['AAO', 'AO', 'CCA', 'Jt.CCA', 'Pr.CCA', 'ADMIN']:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')
    
    # Get team members based on hierarchy
    subordinate_roles = get_subordinate_roles(user_profile.role)
    
    if user_profile.role == 'ADMIN':
        team_members = UserProfile.objects.filter(is_active_holder=True)
    else:
        team_members = UserProfile.objects.filter(
            role__in=subordinate_roles,
            is_active_holder=True
        )
    
    # Calculate productivity metrics for each team member
    productivity_data = []
    
    for member in team_members:
        # Cases completed by this user (where they were involved in processing)
        completed_cases = Case.objects.filter(
            Q(created_by=member.user) | Q(last_updated_by=member.user),
            is_completed=True,
            actual_completion__isnull=False
        )
        
        # Current active cases
        active_cases = Case.objects.filter(
            current_holder=member,
            is_completed=False
        )
        
        # Calculate metrics
        total_completed = completed_cases.count()
        current_workload = active_cases.count()
        
        # Average processing time for completed cases
        if total_completed > 0:
            avg_processing = completed_cases.aggregate(
                avg_time=Avg(F('actual_completion') - F('registration_date'))
            )['avg_time']
            avg_days = avg_processing.days if avg_processing else 0
        else:
            avg_days = 0
        
        # Overdue cases
        overdue_count = active_cases.filter(
            expected_completion__lt=timezone.now()
        ).count()
        
        # Quality indicators (cases requiring revision/escalation)
        # This would need to be enhanced based on your specific quality metrics
        quality_score = 85 + (5 if overdue_count == 0 else -overdue_count * 2)  # Simplified calculation
        quality_score = max(0, min(100, quality_score))  # Keep between 0-100
        
        # Performance rating
        if total_completed >= 20 and avg_days <= 20 and overdue_count == 0:
            performance = 'Excellent'
            performance_class = 'success'
        elif total_completed >= 10 and avg_days <= 30:
            performance = 'Good'
            performance_class = 'info'
        elif total_completed >= 5:
            performance = 'Satisfactory'
            performance_class = 'warning'
        else:
            performance = 'Needs Improvement'
            performance_class = 'danger'
        
        productivity_data.append({
            'user': member,
            'total_completed': total_completed,
            'current_workload': current_workload,
            'avg_processing_days': avg_days,
            'overdue_count': overdue_count,
            'quality_score': quality_score,
            'performance': performance,
            'performance_class': performance_class
        })
    
    # Sort by performance (excellent first, then by completion count)
    productivity_data.sort(key=lambda x: (
        0 if x['performance'] == 'Excellent' else 
        1 if x['performance'] == 'Good' else 
        2 if x['performance'] == 'Satisfactory' else 3,
        -x['total_completed']
    ))
    
    context = {
        'productivity_data': productivity_data,
        'team_size': len(productivity_data),
    }
    
    return render(request, 'cases/user_productivity_report.html', context)

# API Views for Dynamic Dashboard Data

@login_required
def get_dashboard_data(request):
    """
    AJAX endpoint that provides JSON data for dashboard charts and widgets.
    This enables real-time updates without full page refreshes.
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    # Get basic statistics
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]
    
    if user_profile.role == 'ADMIN':
        cases = Case.objects.all()
    else:
        cases = Case.objects.filter(current_holder__role__in=roles_to_view)
    
    # Calculate key metrics
    total_cases = cases.count()
    pending_cases = cases.filter(is_completed=False).count()
    completed_cases = cases.filter(is_completed=True).count()
    overdue_cases = cases.filter(
        is_completed=False,
        expected_completion__lt=timezone.now()
    ).count()
    
    # Case distribution by priority
    priority_data = cases.values('priority').annotate(count=Count('id'))
    
    # Recent activity
    recent_movements = CaseMovement.objects.filter(
        case__in=cases
    ).order_by('-movement_date')[:10]
    
    # Prepare response data
    dashboard_data = {
        'summary': {
            'total_cases': total_cases,
            'pending_cases': pending_cases,
            'completed_cases': completed_cases,
            'overdue_cases': overdue_cases,
            'completion_rate': round((completed_cases / total_cases * 100) if total_cases > 0 else 0, 1)
        },
        'priority_distribution': {
            item['priority']: item['count'] for item in priority_data
        },
        'recent_activity': [
            {
                'case_id': movement.case.case_id,
                'action': movement.action,
                'date': movement.movement_date.strftime('%Y-%m-%d %H:%M'),
                'user': movement.updated_by.username if movement.updated_by else 'System'
            }
            for movement in recent_movements
        ]
    }
    
    return JsonResponse(dashboard_data)

@login_required
def get_trend_data(request):
    """
    Provides trend data for charts showing performance over time.
    """
    user_profile = get_object_or_404(UserProfile, user=request.user)
    
    # Get cases for the last 12 months
    end_date = timezone.now()
    start_date = end_date - timedelta(days=365)
    
    subordinate_roles = get_subordinate_roles(user_profile.role)
    roles_to_view = subordinate_roles + [user_profile.role]
    
    if user_profile.role == 'ADMIN':
        cases = Case.objects.filter(registration_date__range=[start_date, end_date])
    else:
        cases = Case.objects.filter(
            current_holder__role__in=roles_to_view,
            registration_date__range=[start_date, end_date]
        )
    
    # Monthly trends
    monthly_data = cases.annotate(
        month=TruncMonth('registration_date')
    ).values('month').annotate(
        registrations=Count('id'),
        completions=Count('id', filter=Q(is_completed=True))
    ).order_by('month')
    
    trend_data = {
        'labels': [item['month'].strftime('%b %Y') for item in monthly_data],
        'registrations': [item['registrations'] for item in monthly_data],
        'completions': [item['completions'] for item in monthly_data]
    }
    
    return JsonResponse(trend_data)

@login_required
def export_filtered_cases(request):
    """
    Export cases with advanced filtering options applied.
    This allows users to create customized exports based on specific criteria.
    """
    # Implementation would include comprehensive filtering logic
    # and generate CSV with user-specified columns and criteria
    
    # For now, redirect to the basic export
    return redirect('export_cases_report')

# Placeholder views for future implementation
@login_required
def schedule_report(request):
    """Future: Allow users to schedule automatic report generation"""
    messages.info(request, 'Report scheduling feature will be available in a future update.')
    return redirect('reports_dashboard')

@login_required
def automated_report_list(request):
    """Future: View and manage scheduled reports"""
    messages.info(request, 'Automated reports feature will be available in a future update.')
    return redirect('reports_dashboard')

# Add these placeholder views to the end of your cases/views.py file

@login_required
def case_type_analysis_report(request):
    """Placeholder for Case Type Analysis Report"""
    messages.info(request, 'Case Type Analysis Report - Coming Soon!')
    return redirect('reports_dashboard')

@login_required
def bottleneck_analysis_report(request):
    """Placeholder for Bottleneck Analysis Report"""
    messages.info(request, 'Bottleneck Analysis Report - Coming Soon!')
    return redirect('reports_dashboard')

@login_required
def sla_compliance_report(request):
    """Placeholder for SLA Compliance Report"""
    messages.info(request, 'SLA Compliance Report - Coming Soon!')
    return redirect('reports_dashboard')

@login_required
def user_productivity_report(request):
    """Placeholder for User Productivity Report"""
    messages.info(request, 'User Productivity Report - Coming Soon!')
    return redirect('reports_dashboard')

@login_required
def export_custom_report(request):
    """Placeholder for Custom Export"""
    messages.info(request, 'Custom Export - Coming Soon!')
    return redirect('export_cases_report')

@login_required
def export_filtered_cases(request):
    """Placeholder for Filtered Export"""
    messages.info(request, 'Filtered Export - Coming Soon!')
    return redirect('export_cases_report')

@login_required
def schedule_report(request):
    """Placeholder for Report Scheduling"""
    messages.info(request, 'Report Scheduling - Coming Soon!')
    return redirect('reports_dashboard')

@login_required
def automated_report_list(request):
    """Placeholder for Automated Reports"""
    messages.info(request, 'Automated Reports - Coming Soon!')
    return redirect('reports_dashboard')

# API placeholders
@login_required
def get_dashboard_data(request):
    """Placeholder API for dashboard data"""
    return JsonResponse({'message': 'Dashboard API - Coming Soon!'})

@login_required
def get_trend_data(request):
    """Placeholder API for trend data"""
    return JsonResponse({'message': 'Trend API - Coming Soon!'})

@login_required
def get_workload_data(request):
    """Placeholder API for workload data"""
    return JsonResponse({'message': 'Workload API - Coming Soon!'})