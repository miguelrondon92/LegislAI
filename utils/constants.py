# Gemini model used by EnhancedAIAnalyzer; also default for OpsAlert.provider_model.
# Prefer a model with free-tier quota for this API key. As of 2026-08-04 probe:
# gemini-2.0-flash → 429 limit:0; gemini-2.5-flash* → 404 for new users;
# gemini-3.5-flash-lite → PASS (good fit for high-volume chunked analysis).
GEMINI_MODEL = "gemini-3.5-flash-lite"

FEDERAL_POLICY_CATEGORIES = [
  "Agriculture and Food",
  "Arts and Culture",
  "Budget and Fiscal Policy",
  "Civil Rights and Liberties",
  "Commerce and Trade",
  "Communications and Technology",
  "Consumer Protection",
  "Criminal Justice and Law Enforcement",
  "Defense and National Security",
  "Disaster Relief and Emergency Management",
  "Economic Development",
  "Education",
  "Elections and Campaign Finance",
  "Energy",
  "Environment and Natural Resources",
  "Ethics and Government Reform",
  "Financial Services and Banking",
  "Foreign Affairs and Diplomacy",
  "Government Operations",
  "Health Care",
  "Housing and Urban Development",
  "Immigration",
  "Intelligence and Surveillance",
  "International Trade",
  "Labor and Employment",
  "Native American Affairs",
  "Postal Service",
  "Public Lands and Natural Resources",
  "Science and Space",
  "Social Security",
  "Social Services and Welfare",
  "Taxation",
  "Transportation",
  "Veterans Affairs",
  "Water Resources"
]