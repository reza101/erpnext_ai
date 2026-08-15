app_name = "erpnext_ai"
app_title = "Erpnext AI"
app_publisher = "Plus Care"
app_description = "LLM-powered AI features across ERPNext modules"
app_email = "dev@pluscare.com"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

# Includes in <head>
# ------------------

app_include_css = [
	"/assets/erpnext_ai/css/ai_chat_widget.css",
]
app_include_js = [
	"/assets/erpnext_ai/js/ai_chat_widget.js",
]

# Boot Session
# -------------
# Tell the client, per logged-in user, whether it's allowed to render the
# floating chat widget. This is a UX convenience only — the chat API
# endpoint re-checks the same permission server-side on every call.
boot_session = "erpnext_ai.api.chat.extend_boot_session"

# Scheduled Tasks
# ---------------

# scheduler_events = {}

# Testing
# -------

# before_tests = "erpnext_ai.install.before_tests"
