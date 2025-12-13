import requests
import json

# Test Academic Management Routes
base_url = "http://127.0.0.1:5000"

def test_route(route, description):
    """Test a route and return the result"""
    try:
        response = requests.get(f"{base_url}{route}", timeout=5)
        if response.status_code == 200:
            print(f"✓ {description}: {route} - OK")
            return True
        elif response.status_code == 405:
            print(f"- {description}: {route} - Method not allowed (expected for POST-only routes)")
            return True
        elif response.status_code == 302:
            print(f"? {description}: {route} - Redirect (may need authentication)")
            return True
        else:
            print(f"✗ {description}: {route} - Status: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"✗ {description}: {route} - Error: {str(e)}")
        return False

print("=== TESTING ACADEMIC MANAGEMENT ROUTES ===\n")

# Core Academic Management Routes
test_route("/admin/academic/", "Academic Management Dashboard")
test_route("/admin/academic/academic_years", "Academic Years Management")
test_route("/admin/academic/semesters", "Semesters Management")
test_route("/admin/academic/course_batches", "Course Batches Management")
test_route("/admin/academic/subjects", "Enhanced Subjects Management")
test_route("/admin/academic/elective_groups", "Elective Groups Management")
test_route("/admin/academic/faculty_allocations", "Faculty Allocations Management")

print("\n=== TESTING API ENDPOINTS ===\n")

# API Endpoints
test_route("/admin/academic/api/courses", "Courses API")
test_route("/admin/academic/api/semesters", "Semesters API")
test_route("/admin/academic/api/subjects", "Subjects API")
test_route("/admin/academic/api/faculty_workload", "Faculty Workload API")
test_route("/admin/academic/api/curriculum_validation", "Curriculum Validation API")

print("\n=== TESTING ANALYSIS FEATURES ===\n")

# Analysis and Reporting
test_route("/admin/academic/curriculum_analysis", "Curriculum Analysis")
test_route("/admin/academic/faculty_workload_analysis", "Faculty Workload Analysis")
test_route("/admin/academic/generate_time_slots", "Time Slots Generation")

print("\n=== TESTING TIMETABLE INTEGRATION ===\n")

# Timetable Integration
test_route("/admin/academic/timetable_preview", "Timetable Preview")
test_route("/admin/academic/bulk_allocations", "Bulk Faculty Allocations")

print("\n=== TESTING IMPORT/EXPORT FEATURES ===\n")

# Import/Export
test_route("/admin/academic/import_subjects", "Import Subjects")
test_route("/admin/academic/export_curriculum", "Export Curriculum")

print("\n=== TESTING COMPLETED ===")
print("If you see mostly ✓ marks, the academic management system is working correctly!")
print("? marks indicate redirects (usually for authentication)")
print("- marks for Method not allowed are normal for POST-only routes")