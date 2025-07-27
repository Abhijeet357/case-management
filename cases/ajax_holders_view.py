# Add this to your views.py file

@login_required
@require_http_methods(["GET"])
def get_available_holders(request):
    """
    AJAX endpoint to get available holders for case movement
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
        user_profile = get_object_or_404(UserProfile, user=request.user)

        # Check permissions
        if user_profile.role != 'ADMIN' and case.current_holder != user_profile:
            return JsonResponse({
                'success': False,
                'error': 'Permission denied'
            })

        workflow = get_workflow_for_case(case)
        current_index = get_current_stage_index(case, workflow)
        holders = []

        if movement_type == 'forward':
            if current_index < len(workflow) - 1:
                next_stage = workflow[current_index + 1]
                holder_profiles = UserProfile.objects.filter(
                    role=next_stage, 
                    is_active_holder=True
                ).select_related('user')

                holders = [
                    {
                        'id': profile.id,
                        'name': profile.user.get_full_name() or profile.user.username,
                        'role': profile.get_role_display(),
                        'department': profile.department
                    }
                    for profile in holder_profiles
                ]

        elif movement_type == 'backward':
            if current_index > 0:
                prev_stage = workflow[current_index - 1]
                holder_profiles = UserProfile.objects.filter(
                    role=prev_stage, 
                    is_active_holder=True
                ).select_related('user')

                holders = [
                    {
                        'id': profile.id,
                        'name': profile.user.get_full_name() or profile.user.username,
                        'role': profile.get_role_display(),
                        'department': profile.department
                    }
                    for profile in holder_profiles
                ]

        elif movement_type == 'reassign':
            holder_profiles = UserProfile.objects.filter(
                role=case.current_holder.role, 
                is_active_holder=True
            ).exclude(id=case.current_holder.id).select_related('user')

            holders = [
                {
                    'id': profile.id,
                    'name': profile.user.get_full_name() or profile.user.username,
                    'role': profile.get_role_display(),
                    'department': profile.department
                }
                for profile in holder_profiles
            ]

        return JsonResponse({
            'success': True,
            'holders': holders,
            'stage_info': {
                'current_stage': case.current_holder.role,
                'current_index': current_index,
                'workflow': workflow
            }
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
