def detect_domain(skills, designation):

    skills = [s.lower() for s in skills]
    designation = (designation or "").lower()

    skills_text = " ".join(skills)

    domain_map = {

        "software development": [
            "java","spring","hibernate","angular",
            "react","node","microservices","rest",
            "docker","kubernetes","aws","javascript",
            "backend","frontend","developer"
        ],

        "data analytics": [
            "python","sql","powerbi","tableau",
            "pandas","numpy","excel","statistics",
            "data analysis","data analyst"
        ],

        "data science": [
            "machine learning","deep learning",
            "tensorflow","pytorch","nlp","scikit",
            "data science","ml engineer"
        ],

        "cybersecurity": [
            "siem","splunk","nmap","burp",
            "metasploit","owasp","vapt","pentesting"
        ],

        "devops": [
            "docker","kubernetes","jenkins",
            "ci cd","terraform","ansible","devops"
        ],

        "sales": [
            "lead generation","sales closing",
            "crm","cold calling","sales executive"
        ],

        "customer service": [
            "customer support","customer success",
            "call center","customer service"
        ],

        "hr": [
            "recruitment","talent acquisition",
            "payroll","employee engagement","hr"
        ],

        "marketing": [
            "seo","digital marketing",
            "social media marketing","google ads"
        ],

        "finance": [
            "financial analysis","accounting",
            "tally","taxation","finance"
        ],

        "mechanical engineering": [
            "autocad","solidworks","catia",
            "mechanical design"
        ]
    }

    domain_score = {}

    for domain, keywords in domain_map.items():

        score = 0

        for keyword in keywords:

            if keyword in skills_text or keyword in designation:
                score += 1

        domain_score[domain] = score

    best_domain = max(domain_score, key=domain_score.get)

    if domain_score[best_domain] == 0:
        return "other"

    return best_domain