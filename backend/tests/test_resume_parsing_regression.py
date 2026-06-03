import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.ai_parser import build_field_repair_prompt, build_prompt
from backend.experience_engine import process_experience
from backend.services.candidate_intelligence import resume_intelligence_payload
from backend.services.jd_profile_engine import build_jd_profile
from backend.services.parsing_service import parse_resume_enterprise
from backend.services.pipeline import analyze_resume_for_job
from backend.services.resume_quality_gate import apply_parser_quality_gate, build_parser_quality_report
from backend.services.scoring_service import score_candidate


DATA_ANALYST_RESUME = """
VINAYAK HIREMATH
Mob: +91 6361668791 | Email:hgvinay1234@gmail.com
SUMMARY:
Experienced MIS & Data Analyst | 2+ Years in Excel, Power Query, Power BI | e-Commerce
Detail-oriented Data Analyst with 2+ years of experience in reporting, data analysis, and dashboard development.
SKILLS:
MS Excel, Power Query, Power BI, DAX, Python, Pandas, NumPy, SQL, Matplotlib, data reporting, visualization.
WORK EXPERIENCE:
MIS Data Analyst - Levi Strauss & Co Private Limited Bengaluru | Sep '24 - Present
Delivered daily, weekly, and monthly Sell-Through and Stock-on-Hand reports to stakeholders.
Automated daily and weekly sales and return reporting, reducing manual effort by 50%.
Customer Support Analyst - BLP Industry.AI Private Limited Bengaluru | Jun '22 - Jun '24
Developed dashboards and delivered monthly reports for customer engagement.
Customer Support - MIS Executive - BESCOM Bengaluru | Mar '21 - Jun '22
Prepared shift-wise reports with advanced Excel and pivot tables.
Shift Engineer - Mungi Engineers Pvt Ltd Pune | Jun '18 - Jun '20
Automated the logbook process and managed coding assignments and projects on operational data.
EDUCATION
SDM College of Engineering and Technology, Dharwad BE || 8.73 CGPA (May 2015 - June 2018)
CERTIFICATION
Advanced Excel, Power BI Data Analytics, SQL Advanced Certificate
"""


PROJECT_RESUME = """
ANMOL RAI
Email: anmol@example.com
SKILLS
Power BI, SQL, Excel, Python
PROJECTS
Zomato Data Analysis & Power BI Reporting
Created a dynamic Power BI report using DAX metrics and restaurant data.
EDUCATION
Bachelor of Computer Applications 2020 - 2023
"""


SALESFORCE_MULTILINE_RESUME = """
Sean Reynolds
SeanCReynolds1@gmail.com
Experience
Niche Inc.
Pittsburgh, PA(Remote)
Senior Salesforce Developer
Jan 2023 - Present
Created Salesforce automation with Apex Triggers, Flows, LWCs and SOQL.
Freespira
Kirkland, WA
Salesforce Developer I
Jan 2021 - October 2021
Creating custom Apex and Visualforce solutions.
"""


SALESFORCE_DATE_LOCATION_RESUME = """
Eric I. Margules
ericmargules@gmail.com
EXPERIENCE
8/2022-Present, Chicago, IL (Remote)
Lead Software Engineer - Fiserv, Inc.
Delivered software that integrates Fiserv payment processing into Salesforce B2C Commerce.
1/2022-8/2022, Chicago, IL
Software Engineer - Harris Associates L.P.
Built trading systems.
"""


SALESFORCE_ADJACENT_COMPANY_RESUME = """
Rajanya Vazrala
vrajanya@gmail.com
Experience
Sharefest Community Development, Inc.
Salesforce Administrator, Mar 2020 - PRESENT
Implementing new features and best practices in the existing Salesforce NPSP.
Created formulas and automated workflows.
"""


SALESFORCE_CRM_USER_RESUME = """
Dorian Alexander Fong
dorianfong@gmail.com
WORK EXPERIENCE
Cloudflare, Inc. - New Business Development (ASEAN) Jan 2024 - Present
Cloudflare Developer Platform, NinjaPanel, LinkedIn SalesNav, Salesforce (SFDC), SalesLoft
Conducted technical discovery and qualification for sales teams.
Cloudflare, Inc. - Business Development (Greater China Region) May 2023 - Dec 2023
Created and maintained records of leads, prospects and accounts in Salesforce CRM.
Beacon Consulting (Market Research Company) - Telesales/Telemarketer Dec 2019 - Dec 2022
Conducted market research surveys over the phone.
"""


SALESFORCE_INTERNSHIP_SEASON_RESUME = """
Abhijay Mitra
mitraabhijay@gmail.com
INTERNSHIPS
Software Engineering Intern | SALESFORCE
Summer' 21
Project: TeleHealth Application
Integrated Google Speech to Text and Einstein NER APIs.
Software Developer | KHARAGPUR WINTER OF CODE
Winter' 20
Project: Salesforce Batch to Delete Records
Created a Salesforce library using Apex and lightning components. SOQL, SOSL.
COMPETITIONS
Globally Ranked 311 in Google KickStart 2021
EXTRA CURRICULAR ACTIVITIES
Mentor, freshers of the Department of Electrical Engineering 2020 - 2021
"""


SALESFORCE_PIPE_COMPANY_RESUME = """
Gregory Jueves Mayo
gregoryjuevesii23@gmail.com
WORK EXPERIENCE
Windstream | Software Engineer | Little Rock, AR
January 2022 - February 2024
Integrated internal CRM APIs and PAO quote submissions.
Developed features integrating with PAO's pricing database
Domino Data Lab | Software Engineer Intern | San Francisco, CA
April 2021 - October 2021
Built React and Flask deployment tools.
Salesforce | Security Tools Developer Intern | San Francisco, CA
June 2020 - August 2020
Built a Compliance site feature using Node.js.
"""


ICON_EMAIL_AND_UNIVERSITY_WORK_RESUME = """
Vignesh Muthukumar
/phone919-637-2317 /envelopevickymhs@gmail.com
WORK EXPERIENCE
Salesforce, Inc May 2022 - Aug 2022
Software Engineer Intern San Francisco, CA
Built Java and Typescript tooling.
Ninjacart Jun 2019 - Jul 2021
Software Engineer Bangalore, India
Built Java Spring backend services.
North Carolina State University Jan 2022 - Present
Graduate Teaching Assistant, CSC216 - Software Development Fundamentals Raleigh, NC
Hosted labs and graded assignments.
PROJECTS
"""


SALESFORCE_PROFILE_WORD_RESUME = """
Yury Voloshin
yvoloshin01@gmail.com
SALESFORCE DEVELOPER AND ADMINISTRATOR
EXPERIENCE
Fidelus Technologies, Cresskill, NJ
CRM Developer
Salesforce Developer
8/2022 - 3/2024
Configured and maintained user accounts, roles, profiles, permission sets, and single sign-on policy.
SugarCRM Developer
9/2018 - 8/2022
Designed SugarCRM customizations.
Columbia University, New York, NY
Associate Software Developer
7/2017 - 8/2018
Built RESTful online tools.
"""


TWO_COLUMN_RESUME = """
SACHIN YADAV
DATA ANALYST
CONTACT SECTION ABOUT ME
Data Analyst with strong skills in Python, SQL, and Power BI.
Phone: +91 6397447590
E-Mail: sachin.ds.career@gmail.com
Address: Sector 63, Noida ,UP
EXPERIENCE Sep 2024 - Aug 2025
EDUCATION
Digital Marketing Analyst | Infometry Inc (Remote)
Bachelor of Technology 2020-2024
Analyzed marketing data and automated reports, reduced manual effort by 30%.
Infomrmation Technology
Built dashboards (Power BI/Excel) to track KPIs.
ABES Engineering College
SKILLS
Python
SQL
PROJECTS SECTION
Vendor Performance Analysis & Optimization
Power BI
MS Excel Built vendor analytics solution using Python, Pandas, SQL &
Pandas visualization tools.
NumPy Measured key metrics for vendor selection.
Seaborn
inventory control.
Retail Shop Analytics Dashboard (Excel & Power BI)
Data Handling
EDA Built interactive dashboards to analyze sales, inventory & customer trends.
Statistics
Processed POS & inventory data for reporting and visualization.
English Speaking
Problem Solving
LANGUAGE
English
CERTIFICATES
Power BI Data Analyst Professional Certificate
"""


SENIOR_BI_RESUME = """
OLANIKE KAYODE | DATA ANALYST
Mobile: +2347037941216
olanikekayode08@gmail.com
CORE SKILLS
Excel, SQL, R, Power BI, Tableau, data cleaning, statistical analysis, communication, presentation
WORK EXPERIENCE:
DATA ANALYST (VIRTUAL INTERNSHIP)
QUANTUM ANALYTICS NG APR 2023 - PRESENT
Conducted data analysis using Excel, Power BI, Tableau, and SQL.
DATA ANALYST INTERNSHIP
HAGITAL CONSULTING LTD NOV 2022 - APR 2023
Gathered and cleaned datasets from various sources using SQL, R, and Excel.
BUSINESS INTELLIGENCE ANALYST
BEACON OF LIGHT PETROLEUM SERVICES LIMITED FEB 2018 - AUG 2022
Developed dashboards and sales forecasting models for BI reporting.
BUSINESS OPERATION ANALYST
BOVAG PETROLEUM LIMITED JAN 2013 - FEB 2018
Analyzed sales trends, inventory, pricing, and customer retention.
"""


PROJECT_ONLY_ANALYST_RESUME = """
Garv Dudy | Junior Data Analyst | Power BI & SQL
(437) 329 2545 | garvdudy47@gmail.com
Projects
Banking Transactions - Fraud Analytics
Tools: Excel, MySQL, Power BI, ETL Pipelines
- Built an end-to-end ETL pipeline to process global banking transaction data.
- Cleaned 153K rows in Excel, transformed data in MySQL using SQL, and connected the database to Power BI.
FlipMart BI Sales Analytics
Tools: Power BI, Power Query, DAX
- Analyzed 50K retail transactions and built interactive Power BI dashboards with KPIs.
Education
George Brown College - Computer Programming [Toronto, ON | In Progress (Sep 2024 - Apr 2026)]
Vandana International School - High school Diploma (Mathematics & Computer Science) [New Delhi | Apr 2021 - Apr 2023]
Certifications
Microsoft Power BI Data Analyst Professional Certificate [Coursera | In Progress (Oct 2025 - Jan 2026)]
IBM Data Analyst Professional Certificate [Coursera | May 2025 - Sept 2025]
Highlights of Qualifications
- Hands-on experience building ETL pipelines and Power BI dashboards across banking and retail domains.
Skills
SQL, MySQL, Power BI, DAX, Power Query, Python, Pandas, NumPy, Microsoft Excel, Data Cleaning, Reporting
"""


TWO_COLUMN_AMANDA_RESUME = """
A M A N D A P A R T L O W
DATA ANALYST
DATA EXPERIENCE CONTACT
DATA ANALYST 912 399 7521
Nashville Software School | 2020 amandajpartlow@gmail.com
Project Highlights
Capstone - Nashville Public School Disparities: Used Python, SQL, and Tableau to create a school ratings dashboard.
Airplane Etiquette: Used Excel for data cleaning and Tableau to create a travel dashboard.
Baseball Statistics: Used SQL and relational databases to analyze baseball history.
PoKi: Created a Power BI dashboard using Excel and Python from children's poems data.
OTHER PROFESSIONAL EXPERIENCE Microsoft Word, Outlook, PowerPoint
OUTCOMES DATA ANALYST AND PROGRAM COORDINATOR TECHNICAL SKILLS
Girls Inc. of Chattanooga | 2014 - 2020
Oversaw interns who compiled and entered data.
Streamlined outcomes data process for reporting.
EDUCATION
Juggled production orders while UNIVERSITY OF TENNESSEE AT
assisting customers in a fast-paced environment CHATTANOOGA
Bachelor of Science in Middle Grades
"""


TWO_COLUMN_CATHERINE_RESUME = """
D A T A A N A L Y T I C S E X P E R I E N C E
C A T H E R I N E
NASHVILLE SOFTWARE SCHOOL | APPRENTICE DATA ANALYST
MARCH 2020 - JUNE 2020
15-week immersive bootcamp in critical data analytics.
S C H M A L Z E R
D A T A A N A L Y S T
(615) 830-0886 PROJECTS
cat.schmalzer@gmail.com Python: College Tuition and Student Debt - Capstone Project
linkedin.com/in/Catherine-Schmalzer An analysis of college tuition, costs, financial aid options and debt.
github.com/CatSchmalzer to inform choosing the best fit and value for higher education.
Power BI: U.S. Citizen Deaths While Overseas from Non-Natural
Causes - Independent Project
Chose dataset and create a user-friendly, interactive dashboard.
Tableau: UFO Sightings Project - Independent Project
Chose dataset to focus on storytelling and interactive visualizations.
S K I L L S
Excel & PowerPivot
PostgreSQL
Tableau & Power BI
Python, Jupyter Notebooks
V O L U N T E E R / C O M M U N I T Y PostgreSQL: AppTrader Marketing Launch - Group Project
DEPARTMENT HEAD, CREATIVE ARTS,
TN STATE FAIR, 2012 - PRESENT
W O R K E X P E R I E N C E
by partnering with schools around Middle PANERA BREAD
Tennessee ASSOCIATE TRAINER | SEPTEMBER 2013 - PRESENT
Zone Leader during shifts, consistently led bakery/service area.
E D U C A T I O N
BRADLEY UNIVERSITY | PEORIA, ILLINOIS
B.S., Fine Art Photography/Graphic Design; fast-paced environment text
"""


class ResumeParsingRegressionTests(unittest.TestCase):
    def parse_without_llm(self, text):
        with patch("backend.services.parsing_service.parse_resume", return_value={}):
            return parse_resume_enterprise(text)

    def test_smart_quote_work_history_is_generalized(self):
        parsed = self.parse_without_llm(DATA_ANALYST_RESUME.replace("'", "\u2019"))
        exp = process_experience(parsed["experience"])

        self.assertEqual(parsed["location"], "Bengaluru")
        self.assertEqual(exp["last_company_name"], "Levi Strauss & Co Private Limited")
        self.assertEqual(exp["last_working_date"], "Present")
        self.assertGreaterEqual(len(parsed["experience"]), 4)
        self.assertEqual(parsed["projects"], [])

    def test_education_label_data_is_structured(self):
        parsed = self.parse_without_llm(DATA_ANALYST_RESUME)
        education = parsed["education"][0]

        self.assertEqual(education["degree"], "BE")
        self.assertIn("SDM College", education["institution"])
        self.assertEqual(education["start_date"], "May 2015")
        self.assertEqual(education["end_date"], "June 2018")

    @patch("backend.services.pipeline.candidate_embedding_payload", return_value={})
    @patch("backend.services.pipeline.cosine_similarity_cached", return_value=0.82)
    @patch("backend.services.parsing_service.parse_resume", return_value={})
    def test_explicit_role_relevant_experience_caps_total_years(self, *_):
        parsed, exp_data, _ = analyze_resume_for_job(
            DATA_ANALYST_RESUME,
            "Data Analyst role requiring Excel, Power BI, SQL, reporting, dashboards, and data cleaning.",
            ["Excel", "Power BI", "SQL", "Python", "Data Visualization"],
            {"role": "Data Analyst", "min_experience_years": 1, "education": "Bachelor"},
        )

        self.assertEqual(parsed["total_experience_years"], 2.0)
        self.assertGreaterEqual(parsed["relevant_experience_years"], 2.0)
        self.assertEqual(exp_data["last_company_name"], "Levi Strauss & Co Private Limited")

    def test_real_project_section_still_extracts_projects(self):
        parsed = self.parse_without_llm(PROJECT_RESUME)

        self.assertTrue(parsed["projects"])
        self.assertIn("Zomato", parsed["projects"][0]["name"])

    def test_two_column_resume_layout_extracts_role_company_and_projects(self):
        parsed = self.parse_without_llm(TWO_COLUMN_RESUME)
        exp = process_experience(parsed["experience"])
        project_names = [project["name"] for project in parsed["projects"]]

        self.assertEqual(parsed["location"], "Noida")
        self.assertEqual(exp["last_company_name"], "Infometry Inc")
        self.assertEqual(exp["last_working_date"], "Aug 2025")
        self.assertEqual(parsed["education"][0]["degree"], "Bachelor of Technology")
        self.assertEqual(parsed["education"][0]["institution"], "ABES Engineering College")
        self.assertIn("Vendor Performance Analysis & Optimization", project_names)
        self.assertIn("Retail Shop Analytics Dashboard (Excel & Power BI)", project_names)
        self.assertNotIn("Seaborn", project_names)
        self.assertNotIn("Problem Solving", project_names)

    def test_llm_duplicates_are_cleaned_before_profile_save(self):
        llm_parse = {
            "education": [
                {"degree": "Bachelor of Technology 2020-2024", "institution": "ABES Engineering College", "start_date": "2020", "end_date": "2024"},
                {"degree": "Bachelor of Technology", "institution": "ABES Engineering College", "start_date": "2020", "end_date": "2024"},
            ],
            "projects": [
                {"name": "Retail Shop Analytics Dashboard (Excel & Power BI)", "description": "Retail Shop Analytics Dashboard (Excel & Power BI)\nBuilt dashboards.\nPROJECTS SECTION\nPython\nSQL", "technologies": ["Power BI"]},
                {"name": "Retail Shop Analytics Dashboard (Excel & Power BI)", "description": "Built dashboards for sales and inventory reporting.", "technologies": ["Excel"]},
            ],
        }
        with patch("backend.services.parsing_service.parse_resume", return_value=llm_parse):
            parsed = parse_resume_enterprise(TWO_COLUMN_RESUME)

        self.assertEqual(len(parsed["education"]), 1)
        self.assertEqual(len(parsed["projects"]), 1)
        self.assertNotIn("PROJECTS SECTION", parsed["projects"][0]["description"])
        self.assertIn("Power BI", parsed["projects"][0]["technologies"])
        self.assertIn("Excel", parsed["projects"][0]["technologies"])

    def test_audit_invalid_company_phrases_are_not_saved_as_company(self):
        examples = [
            (
                "Nimesh",
                """
                NIMESH VIJAYVARGIYA
                Salesforce Developer
                EXPERIENCE
                improving reporting efficiency and decision-making
                Jan 2021 - Present Salesforce Developer - Flexsin Technologies
                Built Salesforce Apex, LWC and reporting automation.
                """,
                "improving reporting efficiency and decision-making",
            ),
            (
                "Sagnik",
                """
                Sagnik Dutta
                Lead Salesforce Developer
                EXPERIENCE
                SOFTWARE ENGINEERING
                Jan 2018 - Present Lead Salesforce Developer - LTM (Erstwhile LTIMindtree)
                Apex SOQL LWC integrations.
                """,
                "SOFTWARE ENGINEERING",
            ),
            (
                "Pratik",
                """
                PRATIK PRAKASHCHANDRA PANWALA
                Asst-HR Manager
                EXPERIENCE
                Recruitment Process
                Jan 2010 - Present Asst-HR Manager - JEWELEX INDIA PVT LTD. (Arham Gem)
                Handled recruitment sourcing payroll onboarding.
                """,
                "Recruitment Process",
            ),
        ]

        for _, resume_text, invalid_company in examples:
            parsed = self.parse_without_llm(resume_text)
            companies = [item.get("company_name") for item in parsed["experience"]]
            self.assertNotIn(invalid_company, companies)

        valid_resume = """
        Priya Chaudhari
        Software Engineer Lead
        EXPERIENCE
        Capgemini India Private Limited - Software Engineer Lead Jan 2020 - Present
        Built enterprise systems.
        """
        parsed = self.parse_without_llm(valid_resume)
        self.assertIn("Capgemini India Private Limited", [item.get("company_name") for item in parsed["experience"]])

    def test_sachin_education_keeps_courses_out_of_degree_records(self):
        parsed = self.parse_without_llm(
            """
            SACHIN YADAV
            DATA ANALYST
            EDUCATION
            Bachelor of Technology
            ABES Engineering College
            2020-2024
            Data Science Course - CodeWithHarry
            Google Data Analytics Course
            EXPERIENCE
            Digital Marketing Analyst | Infometry Inc (Remote)
            Sep 2024 - Aug 2025
            Analyze dashboards using Power BI SQL Excel.
            """
        )

        education_text = " ".join(" ".join(str(value or "") for value in item.values()) for item in parsed["education"])
        self.assertIn("Bachelor of Technology", education_text)
        self.assertIn("ABES Engineering College", education_text)
        self.assertIn("2020", education_text)
        self.assertIn("2024", education_text)
        self.assertNotIn("Data Science Course", education_text)
        self.assertIn("Data Science Course - CodeWithHarry", parsed["certifications"])

    def test_keyword_only_skills_receive_partial_depth_weight(self):
        jd = "Data Analyst requiring SQL, Power BI, Excel and dashboard work."
        jd_skills = ["SQL", "Power BI", "Excel"]
        profile = build_jd_profile(jd, {"role": "Data Analyst"}, jd_skills)
        parsed = {
            "designation": "Data Analyst",
            "key_skills": ["SQL", "Power BI", "Excel"],
            "total_experience_years": 1,
            "relevant_experience_years": 0,
            "role_relevance_score": 20,
            "experience": [],
            "education": [],
            "projects": [],
            "semantic_score": 0.5,
        }

        result = score_candidate(
            parsed,
            jd,
            profile["must_have_skills"],
            {"role": "Data Analyst"},
            "Skills: SQL, Power BI, Excel.",
            jd_profile=profile,
        )

        self.assertLess(result["mandatory_skill_coverage"], 100)
        self.assertEqual(result["skill_evidence_depth"]["SQL"], "keyword_only")

    def test_stale_score_flag_is_read_only_when_score_delta_exceeds_threshold(self):
        candidate = SimpleNamespace(
            final_score=80,
            scoring_breakdown='{"calibrated_final_score": 62}',
        )
        payload = resume_intelligence_payload(candidate)

        self.assertTrue(payload["stale_score"])
        self.assertEqual(payload["stale_score_delta"], 18.0)

    def test_stacked_role_company_experience_extracts_company(self):
        parsed = self.parse_without_llm(SENIOR_BI_RESUME)
        exp = process_experience(parsed["experience"])

        self.assertEqual(exp["last_company_name"], "QUANTUM ANALYTICS NG")
        self.assertEqual(exp["last_working_date"], "Present")
        self.assertGreaterEqual(exp["total_experience_years"], 10)

    @patch("backend.services.pipeline.candidate_embedding_payload", return_value={})
    @patch("backend.services.pipeline.cosine_similarity_cached", return_value=0.82)
    @patch("backend.services.parsing_service.parse_resume", return_value={})
    def test_jd_experience_range_penalizes_overqualified_fit(self, *_):
        parsed, _, _ = analyze_resume_for_job(
            SENIOR_BI_RESUME,
            "Data Analyst role. Experience: 1-3 Years. Requires Excel, SQL, Power BI, Tableau, data cleaning, communication.",
            ["Excel", "SQL", "Power BI", "Tableau", "Data Cleaning", "Communication"],
            {"role": "Data Analyst", "min_experience_years": 1, "education": "Bachelor"},
        )

        self.assertGreater(parsed["overqualified_penalty"], 0)
        self.assertEqual(parsed["experience_target_max_years"], 3.0)
        self.assertIn("over target experience range", parsed["ranking_reason"])
        self.assertLess(parsed["final_score"], 85)

    def test_project_only_resume_does_not_count_education_or_cert_dates_as_work(self):
        parsed = self.parse_without_llm(PROJECT_ONLY_ANALYST_RESUME)
        exp = process_experience(parsed["experience"])

        self.assertEqual(parsed["full_name"], "Garv Dudy")
        self.assertEqual(exp["total_experience_years"], 0)
        self.assertIsNone(exp["last_company_name"])
        self.assertGreaterEqual(len(parsed["projects"]), 2)

    @patch("backend.services.pipeline.candidate_embedding_payload", return_value={})
    @patch("backend.services.pipeline.cosine_similarity_cached", return_value=0.82)
    @patch("backend.services.parsing_service.parse_resume", return_value={})
    def test_project_only_resume_scores_as_project_fit_not_experienced_fit(self, *_):
        parsed, exp_data, _ = analyze_resume_for_job(
            PROJECT_ONLY_ANALYST_RESUME,
            "Data Analyst role. Experience: 1-3 Years. Requires Excel, SQL, Power BI, Power Query, DAX, reporting, data cleaning.",
            ["Excel", "SQL", "Power BI", "Power Query", "DAX", "Data Cleaning", "Reporting"],
            {"role": "Data Analyst", "min_experience_years": 1, "education": "Bachelor"},
        )

        self.assertEqual(exp_data["total_experience_years"], 0)
        self.assertLess(parsed["experience_score"], 12)
        self.assertLess(parsed["final_score"], 82)

    def test_two_column_spaced_resume_keeps_company_projects_and_name_clean(self):
        parsed = self.parse_without_llm(TWO_COLUMN_AMANDA_RESUME)
        exp = process_experience(parsed["experience"])
        project_names = [project["name"] for project in parsed["projects"]]

        self.assertEqual(parsed["full_name"], "Amanda Partlow")
        self.assertEqual(exp["last_company_name"], "Girls Inc. of Chattanooga")
        self.assertEqual(exp["last_working_date"], "Dec 2020")
        self.assertIn("UNIVERSITY OF TENNESSEE AT CHATTANOOGA", parsed["education"][0]["institution"])
        self.assertIn("Capstone - Nashville Public School Disparities", project_names)
        self.assertIn("PoKi", project_names)
        self.assertNotIn("OTHER PROFESSIONAL EXPERIENCE", " ".join(project_names))

    def test_parser_quality_gate_caps_suspicious_extraction_before_shortlist(self):
        parsed = {
            "full_name": "Technical Skills Microsoft Word PowerPoint",
            "email": "",
            "experience": [{
                "company_name": "grade and observe how feelings impact childhood outcomes OTHER PROFESSIONAL EXPERIENCE",
                "role": "",
                "start_date": "2014",
                "end_date": "2020",
                "description": "OTHER PROFESSIONAL EXPERIENCE Microsoft Word Outlook PowerPoint",
            }],
            "projects": [{
                "name": "OTHER PROFESSIONAL EXPERIENCE",
                "description": "OTHER PROFESSIONAL EXPERIENCE Microsoft Word Outlook PowerPoint",
                "technologies": [],
            }],
            "total_experience_years": 9,
            "resume_quality_score": 90,
            "final_score": 92,
            "rank_score": 90,
            "confidence_score": 82,
            "recommendation": "shortlisted",
            "ranking_reason": "Rank score 90/100.",
        }
        exp_data = {
            "last_company_name": parsed["experience"][0]["company_name"],
            "total_experience_years": 9,
        }

        report = build_parser_quality_report("noisy resume text", parsed, exp_data)
        apply_parser_quality_gate(parsed, exp_data, {}, "noisy resume text")

        self.assertEqual(report["parser_quality_action"], "manual_review_required")
        self.assertLessEqual(parsed["final_score"], 58)
        self.assertLessEqual(parsed["rank_score"], 58)
        self.assertLessEqual(parsed["confidence_score"], 45)
        self.assertEqual(parsed["recommendation"], "in_review")
        self.assertIn("Parser quality gate", parsed["ranking_reason"])

    @patch("backend.services.pipeline.candidate_embedding_payload", return_value={})
    @patch("backend.services.pipeline.cosine_similarity_cached", return_value=0.82)
    @patch("backend.services.pipeline.repair_parse_resume")
    @patch("backend.services.pipeline.repair_parse_fields")
    @patch("backend.services.parsing_service.parse_resume")
    def test_pipeline_recalls_parser_when_quality_gate_finds_bad_parse(self, parse_mock, field_repair_mock, full_repair_mock, *_):
        parse_mock.return_value = {
            "full_name": "Technical Skills Microsoft Word PowerPoint",
            "email": None,
            "key_skills": ["Excel", "SQL", "Power BI"],
            "designation": "Data Analyst",
            "experience": [{
                "company_name": "grade and observe how feelings impact childhood outcomes OTHER PROFESSIONAL EXPERIENCE",
                "role": "",
                "start_date": "2014",
                "end_date": "2020",
                "description": "OTHER PROFESSIONAL EXPERIENCE Microsoft Word Outlook PowerPoint",
            }],
            "education": [],
            "projects": [],
        }
        field_repair_mock.return_value = {
            "full_name": "Amanda Partlow",
            "email": "amandajpartlow@gmail.com",
            "phone": "9123997521",
            "location": "Chattanooga",
            "key_skills": ["Python", "SQL", "Tableau", "Excel", "Power BI"],
            "designation": "Data Analyst",
            "experience": [{
                "company_name": "Girls Inc. of Chattanooga",
                "role": "Outcomes Data Analyst and Program Coordinator",
                "start_date": "2014",
                "end_date": "2020",
                "description": "Streamlined outcomes data process for reporting.",
            }],
            "education": [],
            "projects": [{
                "name": "Capstone - Nashville Public School Disparities",
                "description": "Used Python, SQL, and Tableau to create a dashboard.",
                "technologies": ["Python", "SQL", "Tableau"],
            }],
        }
        full_repair_mock.return_value = None

        parsed, exp_data, _ = analyze_resume_for_job(
            TWO_COLUMN_AMANDA_RESUME,
            "Data Analyst role. Requires Python, SQL, Excel, Power BI, Tableau.",
            ["Python", "SQL", "Excel", "Power BI", "Tableau"],
            {"role": "Data Analyst", "min_experience_years": 1, "education": "Bachelor"},
        )

        self.assertTrue(field_repair_mock.called)
        self.assertFalse(full_repair_mock.called)
        self.assertTrue(parsed["parser_recall_attempted"])
        self.assertTrue(parsed["parser_recall_applied"])
        self.assertEqual(parsed["full_name"], "Amanda Partlow")
        self.assertEqual(exp_data["last_company_name"], "Girls Inc. of Chattanooga")
        self.assertGreater(parsed["final_score"], 68)

    def test_llm_prompts_are_field_level_and_guard_against_company_pollution(self):
        parse_prompt = build_prompt("John Doe\nWORK EXPERIENCE\nAcme | Salesforce Developer | Jan 2021 - Present")
        repair_prompt = build_field_repair_prompt(
            "John Doe\nWORK EXPERIENCE\nAcme | Salesforce Developer | Jan 2021 - Present\nBuilt Apex and SOQL.",
            {"full_name": "John Doe", "experience": [{"company_name": "Built Apex and SOQL", "role": ""}]},
            [{"code": "noisy_experience_company", "message": "Company name looks like a bullet sentence."}],
        )

        self.assertIn("structured work headers", parse_prompt)
        self.assertIn("Salesforce CRM/tool usage is not Salesforce Developer", parse_prompt)
        self.assertIn("PATCH object", repair_prompt)
        self.assertIn("company_name must be a real employer", repair_prompt)
        self.assertIn("Return STRICT JSON only", repair_prompt)

    def test_two_column_heading_name_and_tool_prefixed_projects_are_recovered(self):
        parsed = self.parse_without_llm(TWO_COLUMN_CATHERINE_RESUME)
        exp = process_experience(parsed["experience"])
        project_names = [project["name"] for project in parsed["projects"]]

        self.assertEqual(parsed["full_name"], "Catherine Schmalzer")
        self.assertEqual(exp["last_company_name"], "PANERA BREAD")
        self.assertIn("College Tuition and Student Debt", project_names)
        self.assertIn("U.S. Citizen Deaths While Overseas from Non-Natural", project_names)
        self.assertIn("UFO Sightings Project", project_names)
        self.assertNotIn("Python", project_names)
        self.assertEqual(parsed["education"][0]["degree"], "B.S")
        self.assertEqual(parsed["education"][0]["field"], "Fine Art Photography/Graphic Design")

    def test_multiline_salesforce_experience_keeps_company_not_location(self):
        parsed = self.parse_without_llm(SALESFORCE_MULTILINE_RESUME)
        exp = process_experience(parsed["experience"])

        self.assertEqual(exp["last_company_name"], "Niche Inc")
        self.assertNotIn("Pittsburgh", exp["last_company_name"])
        self.assertEqual(parsed["designation"], "Senior Salesforce Developer")

    def test_date_location_next_line_role_company_experience(self):
        parsed = self.parse_without_llm(SALESFORCE_DATE_LOCATION_RESUME)
        exp = process_experience(parsed["experience"])

        self.assertEqual(exp["last_company_name"], "Fiserv, Inc")
        self.assertNotIn("Chicago", exp["last_company_name"])

    def test_adjacent_company_role_date_experience(self):
        parsed = self.parse_without_llm(SALESFORCE_ADJACENT_COMPANY_RESUME)
        exp = process_experience(parsed["experience"])

        self.assertEqual(exp["last_company_name"], "Sharefest Community Development, Inc")
        self.assertNotIn("Implementing", exp["last_company_name"])

    def test_salesforce_crm_user_resume_keeps_business_development_company_and_role(self):
        parsed = self.parse_without_llm(SALESFORCE_CRM_USER_RESUME)
        exp = process_experience(parsed["experience"])

        self.assertEqual(exp["last_company_name"], "Cloudflare, Inc")
        self.assertIn("Business Development", parsed["designation"])
        self.assertNotEqual(parsed["designation"], "Developer")

    def test_salesforce_seasonal_internships_and_competitions_do_not_become_company(self):
        parsed = self.parse_without_llm(SALESFORCE_INTERNSHIP_SEASON_RESUME)
        exp = process_experience(parsed["experience"])

        self.assertEqual(exp["last_company_name"], "Salesforce, Inc")
        self.assertLess(exp["total_experience_years"], 1)
        self.assertNotIn("freshers", " ".join(job.get("company_name") or "" for job in parsed["experience"]).lower())

    def test_pipe_company_role_location_keeps_real_company(self):
        parsed = self.parse_without_llm(SALESFORCE_PIPE_COMPANY_RESUME)
        exp = process_experience(parsed["experience"])
        companies = [job.get("company_name") for job in parsed["experience"]]

        self.assertEqual(exp["last_company_name"], "Windstream")
        self.assertIn("Domino Data Lab", companies)
        self.assertNotIn("PAO'", companies)

    def test_icon_email_and_university_work_are_cleaned(self):
        parsed = self.parse_without_llm(ICON_EMAIL_AND_UNIVERSITY_WORK_RESUME)
        exp = process_experience(parsed["experience"])

        self.assertEqual(parsed["email"], "vickymhs@gmail.com")
        self.assertEqual(exp["last_company_name"], "North Carolina State University")
        self.assertIn("Ninjacart", [job.get("company_name") for job in parsed["experience"]])

    def test_profile_word_inside_experience_does_not_split_section(self):
        parsed = self.parse_without_llm(SALESFORCE_PROFILE_WORD_RESUME)
        companies = [job.get("company_name") for job in parsed["experience"]]

        self.assertIn("Fidelus Technologies", companies)
        self.assertIn("Columbia University, New York, NY", companies)
        self.assertGreaterEqual(len(parsed["experience"]), 3)


if __name__ == "__main__":
    unittest.main()
