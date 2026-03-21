from django import forms
from .models import StaffProfile, DisciplinaryRecord


class StaffCreateForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    first_name = forms.CharField(max_length=100)
    last_name = forms.CharField(max_length=100)
    role = forms.ChoiceField(choices=StaffProfile.ROLE_CHOICES)
    phone = forms.CharField(max_length=20, required=False)
    hire_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    monthly_salary = forms.DecimalField(max_digits=12, decimal_places=2, initial=0)


class DisciplinaryForm(forms.ModelForm):
    class Meta:
        model = DisciplinaryRecord
        fields = ['severity', 'incident_date', 'description', 'action_taken']
        widgets = {
            'incident_date': forms.DateInput(attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'action_taken': forms.Textarea(attrs={'rows': 3}),
        }
