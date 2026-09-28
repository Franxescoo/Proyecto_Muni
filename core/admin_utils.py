from django.core.exceptions import PermissionDenied

def get_user_organization(request):
    if request.user.is_superuser:
        return None
        
    profile = getattr(request.user, "profile", None)
    
    # Valida si el perfil y su ámbito existen
    if profile is None or profile.organization_id is None:
        raise PermissionDenied("El usuario no posee una organización asignada.")
        
    return profile.organization