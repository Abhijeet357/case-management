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
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from .models import Case, CaseType, CaseTypeTrigger, Record,RecordRequisition,RecordMovement,Location, PPOMaster, UserProfile, CaseMovement, WORKFLOW_STAGES, get_workflow_for_case, get_current_stage_index, get_status_color, FamilyPensionClaim, RetiringEmployee, DynamicFormField,CaseMilestone,CaseMilestoneProgress, CaseFieldData
from .forms import CaseRegistrationForm,CaseMovementForm, UserRegistrationForm, PPOSearchForm, BulkImportForm
from .forms import RecordRequisitionForm, RecordReturnForm

@login_required
def dashboard(request):
    user_profile = get_object_or_404(UserProfile, user=request.user)
    ALLOWED_ROLES_FOR_OVERALL = ['AO', 'Jt.CCA', 'CCA', 'Pr.CCA', 'ADMIN']
    show_overall = user_profile.role in ALLOWED_ROLES_FOR_OVERALL

    # Filtering logic
    cases = Case.objects.all()
    filter_period = request.GET.get('period', '')
    filter_case_type = request.GET.get('case_type', '')
    filter_priority = request.GET.get('priority', '')
    filter_status = request.GET.get('status', '')
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    now = timezone.now()

    # Period filter
    if filter_period == 'today':
        cases = cases.filter(registration_date__date=now.date())
    elif filter_period == 'this_week':
        week_start = now - timedelta(days=now.weekday())
        cases = cases.filter(registration_date__date__gte=week_start.date())
    elif filter_period == 'this_month':
        cases = cases.filter(registration_date__month=now.month, registration_date__year=now.year)
    elif filter_period == 'this_year':
        cases = cases.filter(registration_date__year=now.year)
    elif filter_period == 'custom' and start_date and end_date:
        cases = cases.filter(registration_date__date__gte=start_date, registration_date__date__lte=end_date)

    # Case type filter
    if filter_case_type:
        cases = cases.filter(case_type_id=filter_case_type)
    # Priority filter
    if filter_priority:
        cases = cases.filter(priority=filter_priority)
    # Status filter
    if filter_status == 'pending':
        cases = cases.filter(is_completed=False)
    elif filter_status == 'completed':
        cases = cases.filter(is_completed=True)
    elif filter_status == 'overdue':
        cases = cases.filter(is_completed=False, expected_completion__lt=now)

    filtered_cases = cases.order_by('-registration_date')[:100]  # Limit for performance

    # Stats (recalculate for filtered set)
    total_cases = cases.count()
    pending_cases = cases.filter(is_completed=False).count()
    completed_cases = cases.filter(is_completed=True).count()
    overdue_cases = cases.filter(is_completed=False, expected_completion__lt=now).count()
    high_priority = cases.filter(priority='High', is_completed=False).count()
    medium_priority = cases.filter(priority='Medium', is_completed=False).count()
    low_priority = cases.filter(priority='Low', is_completed=False).count()
    recent_cases = cases.order_by('-registration_date')[:10]
    stage_stats = {}
    for stage in ['DH', 'AAO', 'AO', 'Jt.CCA', 'CCA', 'Pr.CCA']:
        stage_stats[stage] = cases.filter(current_holder__role=stage, is_completed=False).count()

    my_cases = Case.objects.filter(current_holder=user_profile, is_completed=False)

    context = {
        'user_profile': user_profile,
        'show_overall': show_overall,
        'case_types': CaseType.objects.all(),
        'filtered_cases': filtered_cases,
        'filter_period': filter_period,
        'filter_case_type': filter_case_type,
        'filter_priority': filter_priority,
        'filter_status': filter_status,
        'start_date': start_date,
        'end_date': end_date,
        'now': now,
        'total_cases': total_cases,
        'pending_cases': pending_cases,
        'completed_cases': completed_cases,
        'overdue_cases': overdue_cases,
        'high_priority': high_priority,
        'medium_priority': medium_priority,
        'low_priority': low_priority,
        'recent_cases': recent_cases,
        'stage_stats': stage_stats,
        'my_cases': my_cases,
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
    AJAX view to fetch PPO data based on PPO number
    Returns: name_pensioner, pensioner_type, date_of_retirement, mobile_number
    """
    ppo_number = request.GET.get('ppo_number', '').strip()
    
    if not ppo_number:
        return JsonResponse({
            'success': False,
            'error': 'PPO number is required'
        })
    
    try:
        # Try to find PPO in PPOMaster
        ppo_master = PPOMaster.objects.get(ppo_number=ppo_number)
        
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
            'success': True,
            'data': {
                'name_pensioner': ppo_master.employee_name.strip() if ppo_master.employee_name else '',
                'pensioner_type': ppo_master.type_of_pensioner.strip() if hasattr(ppo_master, 'type_of_pensioner') and ppo_master.type_of_pensioner else '',
                'date_of_retirement': formatted_retirement_date,
                'mobile_number': ppo_master.mobile_number.strip() if ppo_master.mobile_number else '',
                'pension_type': ppo_master.pension_type.strip() if ppo_master.pension_type else '',
                'date_of_death': formatted_death_date,
            }
        }
        
        return JsonResponse(data)
        
    except PPOMaster.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'PPO number not found in database'
        })
    
    except Exception as e:
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
                    'type': 'text'
                }
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