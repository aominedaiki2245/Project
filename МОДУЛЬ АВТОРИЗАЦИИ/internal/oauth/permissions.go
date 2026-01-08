package oauth

var rolePermissions = map[string][]string{
	"student": {"view_self", "edit_self"},
	"teacher": {"view_self", "edit_self", "view_users", "assign_tests"},
	"admin":   {"view_self", "edit_self", "view_users", "edit_users", "manage_tests", "all"},
}

func GetPermissionsForRole(role string) []string {
	if perms, ok := rolePermissions[role]; ok {
		return perms
	}
	return []string{"view_self"}
}
