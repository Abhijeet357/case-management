# cases/utils.py - Create this new file

from django.db.models import Count, Q
from django.utils import timezone

class FileSuggestionEngine:
    @staticmethod
    def suggest_files(case_type, user_profile):
        from .models import IndexRegister
        
        case_specific = IndexRegister.objects.filter(
            related_case_types=case_type,
            status='ACTIVE'
        )[:5]
        
        workflow_files = IndexRegister.objects.filter(
            workflow_type=case_type.workflow_type,
            status='ACTIVE'
        )[:5]
        
        return {
            'case_specific': case_specific,
            'workflow_files': workflow_files
        }

class FileWorkflowEngine:
    @staticmethod
    def initialize_workflow(index_file):
        from .models import FileWorkflowStep
        
        templates = {
            'Type_A': [{'step': 'Process', 'role': 'DH', 'days': 2}],
            'Administrative': [{'step': 'Review', 'role': 'AAO', 'days': 1}]
        }
        
        template = templates.get(index_file.workflow_type, [])
        for i, step in enumerate(template):
            FileWorkflowStep.objects.create(
                index_file=index_file,
                step_name=step['step'],
                responsible_role=step['role'],
                step_order=i + 1
            )