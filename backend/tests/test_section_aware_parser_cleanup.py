from unittest.mock import patch
from pathlib import Path
import importlib.util
import json
from types import SimpleNamespace

from backend.experience_engine import process_experience
from backend.routers.job import _candidate_safe_display
from backend.services.parsing_service import parse_resume_enterprise

_regression_spec = importlib.util.spec_from_file_location(
    "resume_regression_fixtures",
    Path(__file__).with_name("test_resume_parsing_regression.py"),
)
_regression = importlib.util.module_from_spec(_regression_spec)
_regression_spec.loader.exec_module(_regression)
TWO_COLUMN_CATHERINE_RESUME = _regression.TWO_COLUMN_CATHERINE_RESUME
DATA_ANALYST_RESUME = _regression.DATA_ANALYST_RESUME


TERESA_RESUME = """
T E R E S A
W H I T E S E L L
teresa.whitesell@example.com
PERSONAL PROFILE
Data-driven analyst using range logs to predict shot placement in long events.

PROJECT HIGHLIGHTS
Ravelry Capstone
Tools: Python, Tableau, Excel, PowerPoint
Analyzed Ravelry data to recommend stock and possible store locations for a local yarn store.

WORK EXPERIENCE
Administrative Assistant and Customer Support Rep | Weight Watchers of Middle and East TN | Jan 2021 - Present
Handled customer support, scheduling, reporting, and administrative coordination.

EDUCATION
Data Analytics Bootcamp - Nashville Software School
BSc (Hons) Food Bioscience - Glasgow Caledonian University
"""


TERESA_OCR_TWO_COLUMN_RESUME = """
TER ESA
W HITESELL
DATA ANALYST
EDUCATION
I have always been motivated to make data-driven decisions from using maps to show
the most shortest route home from school to determining the most efficient way to
accomplish tasks at work.
PER SONAL PR OFILE
SQL
Excel
Tableau
Power BI
Python
TECHNOLOGIES
ADMINISTRATIVE ASSISTANT AND CUSTOMER SUPPORT REP
DATA ANALYTICS EDUCATION
DATA ANALYST
NASHVILLE SOFTW AR E SCHOOL JANUAR Y 2020 - PR ESENT
DATA ANALYTICS BOOTCAMP
Nashville Software School
WORK EXPERIENCE
(615)720-7327
github.com /tfwhitesell
tfwhitesell@ gm ail.com
linkedin.com /in/teresa-whitesell
Ravelry Capstone: using data from ravelry.com, analyze patterns,
yarns and other factors to make recommendations for a local yarn
store when deciding what stock to carry.
Tools used: Python, Tableau, Excel, Powerpoint
Nashville City Cemetery Marketing Presentation: used data on
historic burials to create marketing recommendations to increase
visitor traffic and bring visibility to the cemetery.
Project examples
Tools used: Excel
BSC (HONS) FOOD BIOSCIENCE
Glasgow Caledonian University
Glasgow, Scotland
WEIGHT WATCHERS OF MIDDLE AND EAST TN 2012-2020
Balanced competing priorities to deliver support to company leadership, staff, and customers.
Collected and organized meeting data for 200 weekly meetings for all WW groups.
Delivered weekly internal year-over-year data analysis to company leadership.
"""


MIKE_RESUME = """
M i k e S c h r i e f e r
mike.schriefer11@gmail.com
PROFILE
Former leader using range logs to predict shot placement in long training exercises.

PROJECT EXAMPLES
Powerlifting Dashboard
Tools: Tableau
Created an interactive dashboard comparing results of drug-tested and untested powerlifters.

App Trader Project
Tools: SQL, PowerPoint
Used SQL to filter Apple App Store and Google Play Store data to choose applications for client criteria.

Low Income and Elderly Assistance Project
Tools: Excel
Used US Tax Return Data to determine groups best suited for a grant. Utilized Excel for cleaning and visualization.

WORK EXPERIENCE
Ranger Instructor | US Army | Jan 2015 - Jan 2020
Trained soldiers on range safety and military vehicles.
Dang Brother Pizza | Shift Manager | Feb 2020 - Mar 2022
Managed restaurant operations.

EDUCATION
Nashville Software School - Data Analytics Bootcamp
US Army Ranger School
US Army Basic Leader's Course
"""


MIKE_PDF_TWO_COLUMN_RESUME = """
Mike schriefer
(732) 864-5047
mikeschriefer11@gmail.com
github.com/MikeSchriefer
DATA ANALYST
DATA ANALYTICS EDUCATION
PROFILE
A Data Analyst whose affinity for data stems from using range logs to predict shot placement.
Nashville Software School
Data Analyst March 2020 - present
SKILLS
WORK EXPERIENCE
Python
SQL
Power BI
Tableau
Excel &
PowerPoint
Section Leader Jan 2015 - Jan 2020
US Army
Supervised and led squad of 12 soldiers.
PROJECTS
Low Income and Elderly Assistance Project
Worked with US Tax Return Data to determine which groups would be best suited for a grant.
Utilized Excel for data cleaning/visualization
App Trader Project
Used SQL to filter data from both Apple App Store and Google Play Store.
Powerlifting Dashboard
Created an interactive dashboard with Tableau to compare results of drug tested and untested powerlifters from across world
Manager Dec 2013 - Jan 2015
Dang Brother Pizza and Food Truck Fleet
NFL Player Arrests Dashboard
Created and deployed successful strategies to boost performance,
streamline processes and increase efficiency by creating a system to track inventory.
Visualized the NFL player arrest data to explore trends and gain insights using Power BI
EDUCATION
Nashville Software School
Data Analytics, expected graduation Jun 2020
3 month Data Analytics Bootcamp
US Army Ranger School
"""


NICOLE_RESUME = """
nicole muldowney
muldowneynicole@gmail.com
D A T A A N A L Y S T
P R O F I L E D A T A A N A L Y T I C S E X P E R I E N C E
Numbers and problem solving have been a part of my NASHVILLE SOFTWARE SCHOOL
life for as long as I can remember.
DATA ANALYTICS | M A R C H 2 0 2 0 - J U N E 2 0 2 0
Learned Excel, Python, SQL, Tableau, and Power BI.
P R O J E C T S
N Y C M A R A T H O N - C A P S T O N E P R O J E C T
Created an interactive Tableau dashboard on NYC marathon results over the last five years.
S K I L L S
PYTHON
SQL
POWER BI
N A S H V I L L E B U I L D I N G P E R M I T S - P R O J E C T
TABLEAU
Used Tableau to create dashboards from Nashville building permits data.
ADVANCED EXCEL (PIVOT TABLES, VLOOKUPS)
GOOGLE SHEETS/DOCS/SLIDES Created maps and graphs showing Nashville growth.
W O R K E X P E R I E N C E
SENIOR ACCOUNTANT (CONTRACT ROLE)
V I T A L I T Y L I V I N G | J A N U A R Y 2 0 2 0 - M A R C H 2 0 2 0
Ran reports and analysis through Excel.
SENIOR STAFF ACCOUNTANT
NASHVILLE SOFTWARE SCHOOL WILES + TAYLOR & C O . , P C | J A N U A R Y 2 0 1 4 - N O V E M B E R 2 0 1 9
Analyzed and cleaned sales data.
E D U C A T I O N
Data Analytics Bootcamp, March 2020 - June 2020
BELMONT UNIVERSITY Worked on a collaborative team and recommended strategies for efficiency
BS, Mathematics; 2008 - 2012
Dean's List - 2008 - 2012
"""


NASARIN_RESUME = """
Nasarin Artoul
Nashville, TN | 949.690.4768 | nasarinartoul@gmail.com
Data Analyst
Microsoft Excel | Access | SQL(PostgreSQL) | Python | Tableau | Power BI | Data Analysis
EDUCATION AND CERTIFICATIONS
Nashville School of Software | Nashville, TN Western Kentucky University | Bowling Green, KY
Data Analytics Bootcamp, 2020 Bachelor of Science in Finance, 2016
SQL, Python, Tableau, Power BI Minor in Economics
Capstone Project: Comparing 2008 Recession to
Coronavirus Recession
PROFESSIONAL EXPERIENCE
StrategyCorps | Nashville, TN January 2019 - March 2020
DATA ANALYST
Structured, mined, and cleaned large data sets to identify institutional market trends.
Built VBA macros that normalize addresses, delete extraneous data, and remove unwanted characters.
Wells Fargo Bank | MINNEAPOLIS, MN 2017 - 2019
CREDIT AND RELATIONSHIP MANAGEMENT ANALYST
Created dashboards and performed complex credit analysis.
"""


DIEGO_RESUME = """
DIEGO ALVAREZ
CONTACT WEBSITE
Achieved record low levels of non-performing inventory (NPI) and met Inventory Disposal Expense goals as process
leader, analyzing/reporting data and ensuring timely decisions across all levels of supply chain.
Project Engineer, Merchandising Supply Organization, Hair Care and Color 2013 - 2015
Streaming Service Comparison (Capstone): developed a Tableau dashboard to help users identify the best streaming
service based on their preferences by using data web scraped and manipulated with Python.
ESPN Soccer Power Index (SPI) Evaluation: Analyzed predicted versus actual match results based on SPI system,
identifying possible adjustments to make the algorithm more accurate.
Mobile App Store Analysis: Recommended top mobile apps to invest in to maximize profit from in-app advertising and
purchases, using SQL queries on data from Apple and Android stores.
HR Survey Analysis: Used Power BI to visualize survey results and explore factors contributing to attrition.
IRS Dashboard: Created interactive Excel visualization identifying target areas to assist elderly and low income citizens.
Data Analytics program covering Excel, Python, SQL, Tableau, and Power BI projects:
linkedin.com/in/diegodaa
github.com/diegodaa
Senior Purchases Manager, Global Asset Recovery Purchases 2017 - 2019
954 - 663 - 7854
da.alvarez8@gmail.com
EXPERIENCE
PROCTER & GAMBLE
SKILLS
Project Management
Continuous Improvement
Excel
SQL (PostgreSQL)
Python
Tableau
Power BI
DATA ANALYSIS:
EDUCATION
NASHVILLE SOFTWARE SCHOOL 2020
UNIVERSITY OF FLORIDA 2013
Bachelor of Science in Materials Science and Engineering
Minors in Mathematics & Business Administatrion
"""

DARSHAN_RESUME = """
DARSHAN SARKALE Toronto, Ontario darshansarkale098@gmail.com │ (807) – 358-6709 │ LinkedIn │ Portfolio
EDUCATION
Lakehead University , Canada Sep 2021 – May 2023 Master of Science, Computer Science GPA: 87.33/100
Gujarat Technological University , India Aug 2016 – Sep 2020 Bachelor of Engineering, Information Technology CGPA: 9.44/10
WORK EXPERIENCE
telMAX Inc. , Canada Jan 2025 – Present Technical Support Specialist
Reduced customer churn by 12% by developing Excel and Power BI dashboards for churn analysis and customer feedback trends.
Vosyn , Canada Jan 2024 – Aug 2024 Data Analyst
Improved customer retention by 18% by conducting detailed churn analysis and building interactive Power BI dashboards.
KEY SKILLS
Python, SQL, Power BI, Tableau, Excel, Pandas, NumPy, Power Query, DAX, Data Cleaning, Data Visualization
PROJECTS
Unleashing Insights from Winter Olympics Data - Azure, SQL Server, PowerBI
Engineered and implemented a comprehensive ETL pipeline and optimized data flow for real-time dashboard accessibility.
Customer Churn Analysis of Bank - PowerBI, SQL Deployed Link: Novypro.com
Led development of dynamic Power BI dashboards with KPIs and slicers.
Sales Insights: E-commerce Performance Dashboard - PowerBI, Excel Deployed Link: Novypro.com
Designed and deployed a Power BI dashboard for e-commerce KPIs and profit analysis.
"""


def parse_without_llm(text, ai_parse=None):
    with patch("backend.services.parsing_service.parse_resume", return_value=ai_parse or {}):
        return parse_resume_enterprise(text)


def test_teresa_profile_summary_does_not_become_company_or_project_text():
    parsed = parse_without_llm(TERESA_RESUME)
    exp = process_experience(parsed["experience"])
    project_text = " ".join(project.get("description", "") for project in parsed["projects"])
    education_text = " ".join(" ".join(str(value) for value in item.values()) for item in parsed["education"])

    assert parsed["full_name"] == "Teresa Whitesell"
    assert exp["last_company_name"] == "Weight Watchers of Middle and East TN"
    assert parsed["projects"][0]["name"] == "Ravelry Capstone"
    assert "using range logs" not in project_text.lower()
    assert "Nashville Software School" in education_text
    assert "Glasgow Caledonian University" in education_text


def test_teresa_ocr_two_column_pdf_layout_recovers_clean_profile():
    parsed = parse_without_llm(TERESA_OCR_TWO_COLUMN_RESUME)
    exp = process_experience(parsed["experience"])
    education_text = " ".join(" ".join(str(value) for value in item.values()) for item in parsed["education"])
    project_names = [project["name"] for project in parsed["projects"]]

    assert parsed["full_name"] == "Teresa Whitesell"
    assert parsed["email"] == "tfwhitesell@gmail.com"
    assert parsed["phone"] == "(615)720-7327"
    assert exp["last_company_name"] == "Weight Watchers of Middle and East TN"
    assert exp["total_experience_years"] == 9.01
    assert "Nashville Software School" in education_text
    assert "Glasgow Caledonian University" in education_text
    assert "the most shortest route home" not in education_text
    assert "Ravelry Capstone" in project_names
    assert "Glasgow Caledonian University" not in project_names


def test_mike_project_and_company_boundaries_are_kept_clean():
    parsed = parse_without_llm(MIKE_RESUME)
    exp = process_experience(parsed["experience"])
    project_text = " ".join(project.get("description", "") for project in parsed["projects"])
    education_text = " ".join(" ".join(str(value) for value in item.values()) for item in parsed["education"])

    assert parsed["full_name"] == "Mike Schriefer"
    assert exp["last_company_name"] != "using range logs to predict shot placement in long"
    assert exp["last_company_name"] in {"Dang Brother Pizza", "US Army"}
    assert "Dang Brother Pizza" not in project_text
    assert "Ranger Instructor" not in project_text
    assert "Nashville Software School" in education_text
    assert "US Army Ranger School" in education_text


def test_mike_pdf_two_column_layout_keeps_role_company_and_projects_clean():
    parsed = parse_without_llm(MIKE_PDF_TWO_COLUMN_RESUME)
    exp = process_experience(parsed["experience"])
    project_text = " ".join(project.get("description", "") for project in parsed["projects"])
    project_names = [project["name"] for project in parsed["projects"]]

    assert parsed["full_name"] == "Mike Schriefer"
    assert parsed["phone"] == "(732) 864-5047"
    assert exp["last_company_name"] == "US Army"
    assert "Section Leader" not in {job.get("company_name") for job in parsed["experience"]}
    assert "Powerlifting Dashboard" in project_names
    assert "Low Income and Elderly Assistance Project" in project_names
    assert "App Trader Project" in project_names
    assert "NFL Player Arrests Dashboard" in project_names
    assert "Dang Brother Pizza" not in project_text
    assert "Created and deployed successful strategies" not in project_text


def test_nicole_phone_education_projects_and_last_company_are_clean():
    parsed = parse_without_llm(NICOLE_RESUME)
    exp = process_experience(parsed["experience"])
    education_text = " ".join(" ".join(str(value) for value in item.values()) for item in parsed["education"])
    project_text = " ".join(project.get("description", "") for project in parsed["projects"])
    project_names = [project["name"] for project in parsed["projects"]]

    assert parsed["phone"] == ""
    assert "phone_needs_review" in parsed["parser_flags"]
    assert parsed["safe_display"]["phone"] == "Needs validation"
    assert parsed["field_confidence"]["phone"] < 0.5
    assert exp["last_company_name"] == "Vitality Living"
    assert "Nashville Software School" in education_text
    assert "BELMONT UNIVERSITY" in education_text
    assert "Worked on a collaborative team" not in education_text
    assert "NYC Marathon Capstone Project" in project_names
    assert "Nashville Building Permits Project" in project_names
    assert "ADVANCED EXCEL" not in project_text


def test_nasarin_combined_education_capstone_and_cleaned_data_are_detected():
    parsed = parse_without_llm(NASARIN_RESUME)
    exp = process_experience(parsed["experience"])
    education_text = " ".join(" ".join(str(value) for value in item.values()) for item in parsed["education"])
    project_names = [project["name"] for project in parsed["projects"]]

    assert parsed["phone"] == "949.690.4768"
    assert exp["last_company_name"] == "StrategyCorps"
    assert "Data Cleaning" in parsed["key_skills"]
    assert "SQL" in parsed["key_skills"]
    assert "Nashville School of Software" in education_text
    assert "Western Kentucky University" in education_text
    assert "Data Analytics Bootcamp, 2020 Bachelor" not in education_text
    assert all(not (
        not item.get("degree")
        and "Nashville School of Software" in item.get("institution", "")
        and "Western Kentucky University" in item.get("institution", "")
    ) for item in parsed["education"])
    assert "Comparing 2008 Recession to Coronavirus Recession" in project_names
    assert "Coronavirus Recession" not in [name for name in project_names if name != "Comparing 2008 Recession to Coronavirus Recession"]


def test_diego_layout_noise_does_not_pollute_projects_education_or_company():
    parsed = parse_without_llm(DIEGO_RESUME)
    exp = process_experience(parsed["experience"])
    education_text = " ".join(" ".join(str(value) for value in item.values()) for item in parsed["education"])
    project_text = " ".join(project.get("description", "") for project in parsed["projects"])
    project_names = [project["name"] for project in parsed["projects"]]

    assert parsed["phone"] == "954 - 663 - 7854"
    assert exp["last_company_name"] == "PROCTER & GAMBLE"
    assert "UNIVERSITY OF FLORIDA" in education_text
    assert "Bachelor of Science in Materials Science and Engineering" in education_text
    assert "NASHVILLE SOFTWARE SCHOOL" in education_text or "Nashville Software School" in education_text
    assert "IRS Dashboard" in project_names
    assert "HR Survey Analysis" in project_names
    assert "UNIVERSITY OF FLORIDA" not in project_text
    assert "Bachelor of Science" not in project_text
    assert "Data Analytics program covering" not in project_text
    assert "PERSONAL" not in project_names
    assert not parsed["parser_flags"]


def test_darshan_inline_unicode_layout_recovers_phone_education_projects_and_company():
    parsed = parse_without_llm(DARSHAN_RESUME)
    exp = process_experience(parsed["experience"])
    education_text = " ".join(" ".join(str(value) for value in item.values()) for item in parsed["education"])
    project_names = [project["name"] for project in parsed["projects"]]

    assert parsed["full_name"] == "Darshan Sarkale"
    assert parsed["phone"] == "(807) - 358-6709"
    assert exp["last_company_name"] == "telMAX Inc"
    assert "Lakehead University" in education_text
    assert "Gujarat Technological University" in education_text
    assert "Unleashing Insights from Winter Olympics Data" in project_names
    assert "Customer Churn Analysis of Bank" in project_names
    assert "Sales Insights: E-commerce Performance Dashboard" in project_names
    assert not parsed["parser_flags"]


def test_ai_polluted_fields_are_cleaned_or_replaced_from_sections():
    parsed = parse_without_llm(
        TERESA_RESUME,
        {
            "full_name": "DATA ANALYST",
            "experience": [{
                "company_name": "using range logs to predict shot placement in long",
                "role": "Data Analyst",
                "start_date": "2021",
                "end_date": "Present",
                "description": "PROFILE using range logs",
            }],
            "education": [{"degree": "leadership. Used internal data to create reports", "institution": "WORK EXPERIENCE"}],
            "projects": [{"name": "Ravelry Capstone", "description": "Ravelry Capstone\nWORK EXPERIENCE\nAdministrative Assistant", "technologies": []}],
        },
    )
    exp = process_experience(parsed["experience"])
    project_text = " ".join(project.get("description", "") for project in parsed["projects"])

    assert parsed["full_name"] == "Teresa Whitesell"
    assert exp["last_company_name"] == "Weight Watchers of Middle and East TN"
    assert "leadership" not in str(parsed["education"]).lower()
    assert "WORK EXPERIENCE" not in project_text
    assert parsed["safe_display"]["last_company"] == "Weight Watchers of Middle and East TN"
    assert parsed["field_confidence"]["last_company"] >= 0.8


def test_reliability_layer_marks_low_confidence_instead_of_polluting_fields():
    parsed = parse_without_llm(
        """
        Taylor Morgan
        taylor@example.com
        Profile
        Data analyst with SQL, PostgreSQL, Excel, Power BI, Tableau and data cleaning experience.

        Projects
        Technical Skills
        SQL | PostgreSQL | Excel | Power BI | Tableau | Python | Data Cleaning | Dashboard

        Experience
        2018 - 2022
        """,
        {
            "phone": "2018 - 2022",
            "experience": [{"company_name": "linkedin.com/in/taylor", "role": "Data Analyst", "start_date": "2018", "end_date": "2022"}],
            "education": [{"degree": "Created dashboards and managed reports", "institution": "WORK EXPERIENCE"}],
            "projects": [{"name": "SQL | PostgreSQL | Excel | Power BI | Tableau | Python", "description": "Technical Skills\nSQL | PostgreSQL | Excel | Power BI | Tableau | Python"}],
        },
    )

    assert parsed["phone"] == ""
    assert parsed["safe_display"]["phone"] == "Needs validation"
    assert parsed["safe_display"]["last_company"] == "Needs validation"
    assert parsed["safe_display"]["education"] == "Needs validation"
    assert parsed["safe_display"]["project_evidence"] == "Needs validation"
    assert "profile_needs_review" in parsed["parser_flags"]
    assert "SQL" in parsed["key_skills"]
    assert "Data Cleaning" in parsed["key_skills"]


def test_recruiter_safe_display_hides_polluted_stored_profile_fields():
    candidate = SimpleNamespace(
        phone="2012 - 2016",
        form_phone="",
        last_company_name="Tableau Public/loributler/capstone SQL Excel",
        education="Nashville Software School, managed customers accounts, Data Analytics Bootcamp",
        projects=json.dumps([
            {
                "name": "Met with customers after service to make sure all needs were met.",
                "description": "Met with customers after service to make sure all needs were met.",
                "technologies": [],
            },
            {
                "name": "Sales Dashboard",
                "description": "Analyzed sales data in SQL and Power BI dashboard.",
                "technologies": ["SQL", "Power BI"],
            },
        ]),
        resume_text="",
        total_experience_years=4.0,
    )

    safe = _candidate_safe_display(candidate)

    assert safe["safe_display"]["phone"] == "Needs validation"
    assert safe["safe_display"]["last_company"] == "Needs validation"
    assert safe["safe_display"]["education"] == "Nashville Software School, Data Analytics Bootcamp"
    assert safe["projects"] == [{
        "name": "Sales Dashboard",
        "description": "Analyzed sales data in SQL and Power BI dashboard.",
        "technologies": ["SQL", "Power BI"],
    }]
    assert "phone_needs_review" in safe["parser_flags"]
    assert "company_needs_review" in safe["parser_flags"]


def test_lori_two_column_resume_keeps_role_company_and_project_titles_clean():
    parsed = parse_without_llm(
        """
        LORI BUTLER
        Data Analyst
        loributler818@gmail.com
        Nashville, TN
        PROFILE
        Accounting and payroll manager transitioning into data analysis.
        EXPERIENCE AND WORK HISTORY
        DATA ANALYST APPRENTICE | NASHVILLE SOFTWARE SCHOOL ............. MARCH - JUNE 2020
        Hands-on introduction to analytical tools using 20+ real world datasets.
        CAPSTONE PROJECT - WHAT'S HAPPENING IN MY NEIGHBORHOOD?
        Tools: Python/Jupyter Notebook, Tableau, Excel
        Data: Building permit, zoning, and neighborhood boundaries (data.nashville.gov)
        Managed project from start to finish and strengthened skills in data cleaning, EDA, spatial joins, API, regex, storytelling.
        PROJECT - HANDSUP AMERICA - TEAM LEAD
        Tools: Excel dashboard, pivot tables, dynamic charts
        Data: 2016 U.S. Tax Returns by state, income level, etc.
        Four-person team collaborated via Zoom to create an interactive Excel dashboard.
        ACCTS PAYABLE & PAYROLL MGR | NEPHROLOGY ASSOC | NASHVILLE, TN .... 2016 - 2019
        Improved usability of monthly financial reports by migrating QuickBooks data.
        FOUNDER | BRILLIANT NUMBERS INC | LOS ANGELES, CA ................................2011 - 2015
        Improved financial and business reports for 20+ companies.
        SR ACCOUNTING MGR | INTEGRIEN CORP | LOS ANGELES, CA ...................... 2005 - 2010
        Tech startup that developed predictive analytics software.
        TECHNICAL SKILLS
        Python / Jupyter Notebook
        PostgreSQL
        Tableau
        Power BI
        Microsoft: Excel, Power Pivot, PowerPoint, Word
        EDUCATION
        NASHVILLE SOFTWARE SCHOOL
        Data Analytics
        FLORIDA STATE UNIVERSITY
        Bachelor of Science Degree
        """,
    )
    exp = process_experience(parsed["experience"])
    project_names = {project["name"] for project in parsed["projects"]}

    assert parsed["location"] == "Nashville"
    assert exp["last_company_name"] == "Nephrology Assoc"
    assert parsed["experience"][0]["role"] == "Accts Payable & Payroll Mgr"
    assert "Capstone Project - What's Happening In My Neighborhood?" in project_names
    assert "HandsUp America Excel Dashboard" in project_names
    assert "Data" not in project_names


def test_existing_catherine_and_vinayak_regressions_still_hold():
    catherine = parse_without_llm(TWO_COLUMN_CATHERINE_RESUME)
    vinayak = parse_without_llm(DATA_ANALYST_RESUME)
    catherine_exp = process_experience(catherine["experience"])
    vinayak_exp = process_experience(vinayak["experience"])

    assert catherine["full_name"] == "Catherine Schmalzer"
    assert catherine_exp["last_company_name"] == "PANERA BREAD"
    assert vinayak_exp["last_company_name"] == "Levi Strauss & Co Private Limited"
    assert "leadership" not in str(vinayak["education"]).lower()
