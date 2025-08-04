# cases/context_processors.py

from .models import Grievance, UserProfile

def notifications_context(request):
    """
    Provides global context variables for templates, like notification counts.
    """
    if not request.user.is_authenticated:
        return {}

    try:
        user_profile = request.user.userprofile
        # Calculate the count of NEW grievances assigned to the current user
        new_grievances_count = Grievance.objects.filter(
            assigned_to=user_profile,
            status='NEW'
        ).count()
    except UserProfile.DoesNotExist:
        new_grievances_count = 0

    return {
        'my_new_grievances_count': new_grievances_count,
    }