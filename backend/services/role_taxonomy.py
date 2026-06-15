import re

from backend.services.taxonomy import equivalent_skill, known_skills_in_text, normalize_skill_list


ROLE_FAMILIES = {
    "qa_automation": {
        "patterns": [
            r"\bqa\s+automation\b",
            r"\bautomation\s+(?:test|testing|qa)\b",
            r"\btest\s+automation\b",
            r"\bsdet\b",
            r"\bsoftware\s+development\s+engineer\s+in\s+test\b",
            r"\bquality\s+(?:assurance|engineer)\b",
            r"\bsqa\s+engineer\b",
            r"\bsoftware\s+testing\s+engineer\b",
            r"\bdigital\s+quality\s+assurance\b",
            r"\bsenior\s+quality\s+engineer\b",
        ],
        "skills": [
            "Selenium", "Cypress", "Playwright", "TestNG", "JUnit", "Java", "Python",
            "JavaScript", "Automation Testing", "Manual Testing", "API Testing", "Postman",
            "REST Assured", "SQL", "Jira", "Git", "Jenkins", "CI/CD", "Test Cases",
            "Regression Testing",
        ],
        "default_must_have": [
            "Automation Testing", "Manual Testing", "API Testing", "Test Cases",
            "Bug Reporting", "Selenium", "Postman", "SQL",
        ],
        "default_core_groups": {
            "ui_automation": ["Selenium", "Cypress", "Playwright"],
            "api_testing": ["API Testing", "Postman", "REST Assured", "Swagger", "SoapUI"],
            "test_frameworks": ["TestNG", "JUnit", "Pytest", "Cucumber", "BDD"],
            "testing_process": ["Manual Testing", "Automation Testing", "Regression Testing", "Smoke Testing", "Sanity Testing", "Test Cases", "Test Plan", "Bug Reporting", "STLC", "SDLC"],
            "programming": ["Java", "Python", "JavaScript"],
            "database_validation": ["SQL", "MySQL", "PostgreSQL", "SQL Server", "Database Testing"],
            "delivery_tools": ["Jira", "Git", "GitHub", "Jenkins", "CI/CD", "GitHub Actions", "GitLab CI"],
        },
        "core_groups": {
            "ui_automation": ["Selenium", "Cypress", "Playwright"],
            "api_testing": ["API Testing", "Postman", "REST Assured", "Swagger", "SoapUI"],
            "test_frameworks": ["TestNG", "JUnit", "Pytest", "Cucumber", "BDD"],
            "testing_process": ["Manual Testing", "Automation Testing", "Regression Testing", "Smoke Testing", "Sanity Testing", "Test Cases", "Test Plan", "Bug Reporting", "STLC", "SDLC"],
            "programming": ["Java", "Python", "JavaScript"],
            "database_validation": ["SQL", "MySQL", "PostgreSQL", "SQL Server", "Database Testing"],
            "delivery_tools": ["Jira", "Git", "GitHub", "Jenkins", "CI/CD", "GitHub Actions", "GitLab CI"],
        },
    },
    "manual_qa": {
        "patterns": [
            r"\bmanual\s+qa\b",
            r"\bmanual\s+test(?:er|ing)\b",
            r"\bqa\s+engineer\b",
            r"\btest\s+engineer\b",
            r"\bquality\s+assurance\s+analyst\b",
        ],
        "skills": ["Manual Testing", "Functional Testing", "Regression Testing", "Test Cases", "Test Plan", "Bug Reporting", "Jira", "STLC", "SDLC"],
        "core_groups": {
            "testing_process": ["Manual Testing", "Functional Testing", "Regression Testing", "Smoke Testing", "Sanity Testing"],
            "test_design": ["Test Cases", "Test Plan", "Test Scenarios"],
            "defect_tracking": ["Bug Reporting", "Defect Life Cycle", "Jira"],
        },
    },
    "dotnet_full_stack": {
        "patterns": [
            r"\b(?:senior\s+|lead\s+|principal\s+)?(?:\.net|dotnet)\s+full[-\s]?stack\b",
            r"\bfull[-\s]?stack\b.*\b(?:\.net|dotnet|c#|asp\.?\s*net)\b",
            r"\b(?:\.net|dotnet|asp\.?\s*net|c#)\b.*\bangular\b",
            r"\b(?:senior\s+|lead\s+)?(?:\.net|dotnet|asp\.?\s*net|c#)\s+(?:developer|engineer)\b",
            r"\benterprise\s+(?:\.net|dotnet)\s+engineer\b",
        ],
        "skills": [
            ".NET", ".NET Core", ".NET Framework", "ASP.NET", "ASP.NET Core",
            "ASP.NET MVC", "C#", "Web API", "ASP.NET Web API", "REST API",
            "RESTful APIs", "Entity Framework", "LINQ", "ADO.NET", "Angular",
            "AngularJS", "TypeScript", "JavaScript", "HTML", "CSS", "Bootstrap",
            "Kendo UI", "Telerik", "SQL Server", "MS SQL", "SQL", "Stored Procedures",
            "SQL Performance Tuning", "Database Optimization", "PL/SQL", "T-SQL",
            "Git", "GitHub", "Azure DevOps", "CI/CD", "Jenkins", "Agile", "Scrum",
            "Jira", "Azure", "Redis", "Distributed Caching", "OAuth", "OpenID Connect",
            "SSO", "Authentication", "Authorization", "Microservices", "Docker",
            "Cursor", "Devin",
        ],
        "default_must_have": [
            ".NET Core", "C#", "ASP.NET Core", "Web API", "Angular", "SQL Server", "Git",
        ],
        "default_core_groups": {
            "backend": [".NET Core", "ASP.NET Core", ".NET Framework", "ASP.NET MVC", "C#", "Web API", "ASP.NET Web API", "REST API", "RESTful APIs", "Entity Framework", "LINQ", "ADO.NET"],
            "frontend": ["Angular", "AngularJS", "TypeScript", "JavaScript", "HTML", "CSS", "Bootstrap", "Kendo UI", "Telerik"],
            "database": ["SQL Server", "MS SQL", "SQL", "Stored Procedures", "SQL Performance Tuning", "Database Optimization", "PL/SQL", "T-SQL"],
            "deployment_tools": ["Git", "GitHub", "Azure DevOps", "CI/CD", "Jenkins", "Agile", "Scrum", "Jira"],
        },
        "default_nice_to_have": [
            "Azure", "Redis", "Distributed Caching", "OAuth", "OpenID Connect", "SSO",
            "Authentication", "Authorization", "Microservices", "Docker", "Cloud",
            "Cursor", "Devin",
        ],
        "core_groups": {
            "backend": [".NET Core", "ASP.NET Core", ".NET Framework", "ASP.NET MVC", "C#", "Web API", "ASP.NET Web API", "REST API", "RESTful APIs", "Entity Framework", "LINQ", "ADO.NET"],
            "frontend": ["Angular", "AngularJS", "TypeScript", "JavaScript", "HTML", "CSS", "Bootstrap", "Kendo UI", "Telerik"],
            "database": ["SQL Server", "MS SQL", "SQL", "Stored Procedures", "SQL Performance Tuning", "Database Optimization", "PL/SQL", "T-SQL"],
            "deployment_tools": ["Git", "GitHub", "Azure DevOps", "CI/CD", "Jenkins", "Agile", "Scrum", "Jira"],
            "auth_security": ["OAuth", "OpenID Connect", "SSO", "Authentication", "Authorization", "RBAC", "JWT", "Identity Server", "Azure AD"],
            "good_to_have": ["Azure", "Redis", "Distributed Caching", "Microservices", "Docker", "Cloud", "Cursor", "Devin"],
        },
    },
    "software_backend": {
        "patterns": [
            r"\bbackend\b",
            r"\bback[-\s]?end\b",
            r"\bpython\s+developer\b",
            r"\bjava\s+developer\b",
            r"\bapi\s+developer\b",
            r"\bnode(?:\.js)?\s+developer\b",
            r"\bspring\s+boot\s+developer\b",
            r"\bsoftware\s+engineer\b",
        ],
        "skills": [
            "Python", "Java", "Node.js", "FastAPI", "Django", "Flask", "Spring Boot",
            "PHP", "Laravel", "SQL", "PostgreSQL", "MySQL", "MongoDB", "REST API",
            "JWT", "OAuth", "Authentication", "Git", "Postman", "Docker", "Linux",
        ],
        "default_must_have": [
            "REST API", "Authentication", "Database Design", "Git", "Postman",
        ],
        "default_core_groups": {
            "backend_path": ["Node.js", "Express", "Python", "Django", "FastAPI", "Flask", "Java", "Spring Boot", "PHP", "Laravel"],
            "api_logic": ["REST API", "GraphQL", "CRUD", "API Integration", "Business Logic"],
            "database": ["SQL", "PostgreSQL", "MySQL", "MongoDB", "SQL Server", "Database Design"],
            "api_auth": ["JWT", "OAuth", "Spring Security", "Authentication", "Authorization", "RBAC", "Session Auth", "Firebase Auth", "Auth0", "AWS Cognito", "Clerk Auth", "Password Hashing", "Access Control", "Token Auth", "MFA"],
            "tooling_deployment": ["Git", "GitHub", "Postman", "Swagger", "OpenAPI", "Docker", "Kubernetes", "AWS", "Azure", "DigitalOcean", "Render", "Nginx", "Linux", "CI/CD"],
            "reliability_security": ["Logging", "Error Handling", "Validation", "Rate Limiting", "Security"],
        },
        "default_nice_to_have": [
            "TypeScript", "Docker", "Redis", "Kafka", "RabbitMQ", "Celery", "BullMQ",
            "CI/CD", "AWS", "Azure", "DigitalOcean", "Nginx", "Linux", "Microservices",
        ],
        "core_groups": {
            "backend_path": ["Node.js", "Express", "Python", "Django", "FastAPI", "Flask", "Java", "Spring Boot", "PHP", "Laravel"],
            "api_logic": ["REST API", "GraphQL", "CRUD", "API Integration", "Business Logic"],
            "database": ["SQL", "PostgreSQL", "MySQL", "MongoDB", "SQL Server", "Database Design"],
            "api_auth": ["JWT", "OAuth", "Spring Security", "Authentication", "Authorization", "RBAC", "Session Auth", "Firebase Auth", "Auth0", "AWS Cognito", "Clerk Auth", "Password Hashing", "Access Control", "Token Auth", "MFA"],
            "tooling_deployment": ["Git", "GitHub", "Postman", "Swagger", "OpenAPI", "Docker", "Kubernetes", "AWS", "Azure", "DigitalOcean", "Render", "Nginx", "Linux", "CI/CD"],
            "reliability_security": ["Logging", "Error Handling", "Validation", "Rate Limiting", "Security"],
        },
    },
    "software_frontend": {
        "patterns": [
            r"\bfrontend\b",
            r"\bfront[-\s]?end\b",
            r"\bui\s+developer\b",
            r"\breact\s+(?:developer|engineer)\b",
            r"\breact\s+ui\s+developer\b",
            r"\bweb\s+front[-\s]?end\b",
        ],
        "skills": [
            "HTML", "HTML5", "CSS", "CSS3", "JavaScript", "ES6", "React", "React.js",
            "JSX", "Responsive Design", "Mobile-first Design", "Browser Compatibility",
            "REST API", "API Integration", "Fetch", "Axios", "Redux", "Context API",
            "Zustand", "Git", "GitHub", "GitLab", "npm", "Vite", "Webpack",
            "Chrome DevTools", "Performance Optimization", "Web Vitals", "Debugging",
            "TypeScript", "Next.js", "Tailwind CSS", "Bootstrap", "Material UI",
            "Jest", "React Testing Library", "Cypress", "SEO", "Accessibility",
            "Vercel", "Netlify", "AWS", "Node.js", "Express",
        ],
        "default_must_have": [
            "HTML", "CSS", "JavaScript", "React", "Responsive Design",
            "REST API", "Redux", "Git", "Vite", "Performance Optimization",
        ],
        "default_core_groups": {
            "frontend_core": ["HTML", "HTML5", "CSS", "CSS3", "JavaScript", "ES6"],
            "react_core": ["React", "React.js", "ReactJS", "JSX", "Component-based Development"],
            "responsive_ui": ["Responsive Design", "Mobile-first Design", "Cross-browser Compatibility", "Browser Compatibility", "UI/UX", "Accessibility"],
            "api_integration": ["REST API", "REST APIs", "API Integration", "Dynamic Data-driven Interfaces", "Fetch", "Axios", "TanStack Query"],
            "state_management": ["Redux", "Context API", "Zustand", "Jotai", "Recoil", "MobX"],
            "frontend_tooling": ["Git", "GitHub", "GitLab", "npm", "Vite", "Webpack", "Build Tools", "Chrome DevTools"],
            "performance_debugging": ["Performance Optimization", "Page Speed", "Web Vitals", "Debugging", "Browser Debugging", "Code Quality"],
        },
        "default_nice_to_have": [
            "TypeScript", "Next.js", "Tailwind CSS", "Bootstrap", "Material UI",
            "Styled Components", "Storybook", "Jest", "React Testing Library",
            "Cypress", "SEO", "Accessibility", "Vercel", "Netlify", "AWS",
            "Node.js", "Express",
        ],
        "core_groups": {
            "frontend_core": ["HTML", "HTML5", "CSS", "CSS3", "JavaScript", "ES6"],
            "react_core": ["React", "React.js", "ReactJS", "JSX", "Component-based Development"],
            "responsive_ui": ["Responsive Design", "Mobile-first Design", "Cross-browser Compatibility", "Browser Compatibility", "UI Implementation", "UI/UX", "Accessibility"],
            "api_integration": ["REST API", "REST APIs", "API Integration", "Dynamic Data-driven Interfaces", "Fetch", "Axios", "TanStack Query"],
            "state_management": ["Redux", "Context API", "Zustand", "Jotai", "Recoil", "MobX"],
            "frontend_tooling": ["Git", "GitHub", "GitLab", "npm", "Vite", "Webpack", "Build Tools", "Chrome DevTools"],
            "performance_debugging": ["Performance Optimization", "Page Speed", "Web Vitals", "Debugging", "Browser Debugging", "Code Quality"],
            "good_to_have": ["TypeScript", "Next.js", "Tailwind CSS", "Bootstrap", "Material UI", "Styled Components", "Storybook", "Jest", "React Testing Library", "Cypress", "SEO", "Accessibility", "Vercel", "Netlify", "AWS", "Node.js", "Express"],
        },
    },
    "full_stack": {
        "patterns": [
            r"\bfull[-\s]?stack\b",
            r"\bfull\s+stack\s+web\s+developer\b",
            r"\bweb\s+developer\b",
            r"\bmern\b",
            r"\bmean\b",
            r"\breact\b.*\bnode\b|\bnode\b.*\breact\b",
        ],
        "skills": [
            "JavaScript", "TypeScript", "React", "Next.js", "Vue", "Angular", "HTML", "CSS",
            "Node.js", "Express", "Django", "FastAPI", "PHP", "Laravel", "Spring Boot",
            "REST API", "MongoDB", "MySQL", "PostgreSQL", "SQL", "Git", "Docker", "AWS",
        ],
        "default_must_have": ["JavaScript", "React", "Node.js", "REST API", "MongoDB", "SQL", "Git"],
        "default_core_groups": {
            "frontend": ["React", "Next.js", "Vue", "Angular"],
            "frontend_foundation": ["HTML", "CSS", "JavaScript", "TypeScript"],
            "backend": ["Node.js", "Express", "Django", "FastAPI", "PHP", "Laravel", "Java", "Spring Boot"],
            "database": ["MongoDB", "Mongoose", "MySQL", "PostgreSQL", "SQL", "SQL Server", "Firebase", "Firestore", "Prisma", "Sequelize"],
            "api_auth": ["REST API", "GraphQL", "JWT", "OAuth", "Authentication", "Authorization", "RBAC", "Session Auth", "Firebase Auth", "Clerk Auth", "Password Hashing"],
            "deployment_tools": ["Git", "GitHub", "GitHub Actions", "Docker", "Kubernetes", "AWS", "Azure", "DigitalOcean", "Vercel", "Netlify", "Render", "Heroku", "Nginx", "Linux", "VPS", "CI/CD"],
        },
        "default_nice_to_have": [
            "TypeScript", "Next.js", "Docker", "CI/CD", "AWS", "Vercel", "Netlify",
            "DigitalOcean", "Nginx", "Linux", "JWT", "OAuth", "Postman", "Tailwind CSS", "Bootstrap",
        ],
        "core_groups": {
            "frontend": ["React", "Next.js", "Angular", "Vue"],
            "frontend_foundation": ["HTML", "CSS", "JavaScript", "TypeScript"],
            "backend": ["Node.js", "Express", "Python", "Django", "FastAPI", "Flask", "PHP", "Laravel", "Java", "Spring Boot", "REST API"],
            "database": ["SQL", "PostgreSQL", "MySQL", "MongoDB", "Mongoose", "SQL Server", "Firebase", "Firestore", "Prisma", "Sequelize"],
            "api_auth": ["REST API", "GraphQL", "JWT", "OAuth", "Authentication", "Authorization", "RBAC", "Session Auth", "Firebase Auth", "Clerk Auth", "Password Hashing"],
            "deployment_tools": ["Git", "GitHub", "GitHub Actions", "Docker", "Kubernetes", "AWS", "Azure", "DigitalOcean", "Vercel", "Netlify", "Render", "Heroku", "Nginx", "Linux", "VPS", "CI/CD"],
        },
    },
    "mobile_development": {
        "patterns": [r"\bmobile\b", r"\bandroid\b", r"\bios\b", r"\breact\s+native\b", r"\bflutter\b"],
        "skills": ["Android", "iOS", "Kotlin", "Swift", "React Native", "Flutter"],
        "core_groups": {
            "platform": ["Android", "iOS", "React Native", "Flutter"],
            "language": ["Kotlin", "Swift", "Java", "Dart", "JavaScript"],
        },
    },
    "data_analytics": {
        "patterns": [
            r"\bdata\s+analyst\b",
            r"\bmis\s+analyst\b",
            r"\bbi\s+analyst\b",
            r"\bbusiness\s+intelligence\s+analyst\b",
            r"\breporting\s+analyst\b",
            r"\bpower\s*bi\s+(?:analyst|developer)\b",
            r"\banalytics\b",
            r"\breporting\b",
            r"\bdashboards?\b",
        ],
        "skills": [
            "SQL",
            "Excel",
            "Power BI",
            "Tableau",
            "Dashboard",
            "MIS Reporting",
            "KPI",
            "Data Analysis",
            "Data Cleaning",
            "Power Query",
            "DAX",
        ],
        "default_must_have": ["SQL", "Excel", "Data Analysis", "Data Visualization", "Reporting"],
        "default_core_groups": {
            "querying": ["SQL"],
            "spreadsheet": ["Excel", "Advanced Excel"],
            "bi_tool": ["Power BI", "Tableau", "Looker"],
            "reporting": ["MIS Reporting", "Dashboard", "KPI", "Business Reporting", "Reporting"],
        },
        "default_nice_to_have": [
            "Power BI",
            "Tableau",
            "Power Query",
            "DAX",
            "Python",
            "Pandas",
            "Statistics",
            "Data Cleaning",
            "KPI",
            "MIS Reporting",
            "Business Reporting",
        ],
        "core_groups": {
            "querying": ["SQL"],
            "spreadsheet": ["Excel", "Advanced Excel"],
            "bi_tool": ["Power BI", "Tableau", "Looker"],
            "reporting": ["MIS Reporting", "Dashboard", "KPI", "Business Reporting"],
        },
    },
    "applied_ml_engineer": {
        "patterns": [
            r"\bapplied\s+(?:ml|machine\s+learning)\s+engineer\b",
            r"\bcomputer\s+vision\b",
            r"\bdocument\s+ai\b",
            r"\bocr\b",
            r"\bvision[-\s]?language\s+models?\b",
            r"\bvlm\b",
            r"\bmultimodal\b",
            r"\binference\s+optimization\b",
            r"\bmodel\s+(?:serving|deployment|benchmarking|evaluation)\b",
            r"\bimage\s+(?:processing|enhancement|recognition|classification|segmentation)\b",
        ],
        "skills": [
            "Machine Learning", "Deep Learning", "Python", "PyTorch", "TensorFlow",
            "Scikit-learn", "Hugging Face", "Transformers", "Computer Vision",
            "OpenCV", "OCR", "Document AI", "Tesseract", "PaddleOCR", "DocTR",
            "TrOCR", "OMR", "YOLO", "R-CNN", "Image Processing", "Image Enhancement",
            "Object Detection", "Image Classification", "Segmentation", "MONAI",
            "NLP", "LLM", "Generative AI", "RAG", "LangChain", "LlamaIndex",
            "VLM", "Multimodal AI", "CLIP", "DINO", "BLIP", "vLLM",
            "MLOps", "LLMOps", "MLflow", "Docker", "Kubernetes", "FastAPI",
            "Model Deployment", "Model Serving", "Inference Pipeline",
            "Latency Optimization", "Cost Optimization", "Regression Testing",
        ],
        "default_must_have": [
            "Machine Learning", "Deep Learning", "Python", "PyTorch",
            "Computer Vision", "OCR", "Document AI", "LLM", "RAG",
            "Multimodal AI", "MLOps", "Model Deployment",
        ],
        "default_core_groups": {
            "ml_dl_fundamentals": ["Machine Learning", "Deep Learning", "Python", "PyTorch", "TensorFlow", "Scikit-learn", "Model Evaluation", "Model Benchmarking"],
            "cv_ocr_document_ai": ["Computer Vision", "OCR", "Document AI", "OpenCV", "Image Processing", "Object Detection", "Image Classification", "Segmentation", "YOLO", "R-CNN", "PaddleOCR", "Tesseract", "TrOCR", "DocTR", "OMR", "Handwriting Recognition", "Label Extraction", "Image Enhancement", "Real-ESRGAN"],
            "llm_nlp_vlm_multimodal": ["NLP", "LLM", "Generative AI", "RAG", "LangChain", "LlamaIndex", "Hugging Face", "Transformers", "VLM", "Multimodal AI", "Vision-Language Model", "CLIP", "DINO", "BLIP", "vLLM", "Fine-tuning", "Prompt Engineering"],
            "production_ml_mlops": ["MLOps", "LLMOps", "MLflow", "Docker", "Kubernetes", "FastAPI", "Flask", "Model Deployment", "Model Serving", "Inference Pipeline", "CI/CD", "SageMaker", "Vertex AI", "Azure ML", "Monitoring", "Latency Optimization", "Cost Optimization", "Production"],
        },
        "default_nice_to_have": [
            "Real-ESRGAN", "SDXL", "Whisper", "IndicTrans2", "NLLB", "Vector Database",
            "Pinecone", "Chroma", "FAISS", "LoRA", "qLoRA", "Bedrock",
        ],
        "core_groups": {
            "ml_dl_fundamentals": ["Machine Learning", "Deep Learning", "Python", "PyTorch", "TensorFlow", "Scikit-learn", "Model Training", "Model Evaluation", "Model Benchmarking", "Regression Testing"],
            "cv_ocr_document_ai": ["Computer Vision", "OCR", "Document AI", "OpenCV", "Image Processing", "Object Detection", "Image Classification", "Segmentation", "YOLO", "R-CNN", "Faster R-CNN", "Mask R-CNN", "CNN", "ViT", "MONAI", "Medical Imaging", "PaddleOCR", "Tesseract", "TrOCR", "DocTR", "EasyOCR", "OMR", "Handwriting Recognition", "Form Recognition", "Table Recognition", "Receipt Extraction", "Invoice Extraction", "Label Extraction", "QR Extraction", "Document VQA", "Image Enhancement", "Real-ESRGAN"],
            "llm_nlp_vlm_multimodal": ["NLP", "LLM", "Generative AI", "GenAI", "RAG", "LangChain", "LlamaIndex", "GPT", "Llama", "Mistral", "Gemini", "Hugging Face", "Transformers", "VLM", "Multimodal AI", "Vision-Language Model", "CLIP", "DINO", "BLIP", "vLLM", "Fine-tuning", "LoRA", "qLoRA", "Prompt Engineering", "Vector Database", "Pinecone", "Chroma", "FAISS"],
            "production_ml_mlops": ["MLOps", "LLMOps", "MLflow", "Docker", "Kubernetes", "FastAPI", "Flask", "Model Deployment", "Model Serving", "Inference Pipeline", "CI/CD", "GitHub Actions", "SageMaker", "Bedrock", "Vertex AI", "Azure ML", "Cloud Run", "Lambda", "Monitoring", "Latency Optimization", "Cost Optimization", "Autoscaling", "Production"],
        },
    },
    "product_software_architect": {
        "patterns": [
            r"\b(?:senior\s+|lead\s+|principal\s+)?architect\s*[-/]\s*product\s+engineering\b",
            r"\bproduct\s+engineering\s+architect\b",
            r"\bsoftware\s+architect\b",
            r"\bbackend\s+architect\b",
            r"\btechnical\s+architect\b",
            r"\bsolution\s+architect\b.*\b(?:hands[-\s]?on|coding|backend|api|product)\b",
            r"\bprincipal\s+(?:software\s+)?engineer\b.*\b(?:architecture|system\s+design|scalability)\b",
            r"\bstaff\s+(?:software\s+)?engineer\b.*\b(?:architecture|system\s+design|scalability)\b",
        ],
        "skills": [
            "Software Architecture", "System Design", "Backend Architecture",
            "API Design", "REST API", "Distributed Systems", "Scalability",
            "Performance Optimization", "Security", "Node.js", "Python",
            "Express", "FastAPI", "Django", "SQL", "PostgreSQL", "MongoDB",
            "Microservices", "Docker", "Kubernetes", "CI/CD", "AWS", "Azure",
            "Product Engineering", "Startup Experience", "0-to-1 Product",
            "B2B SaaS", "Technical Leadership", "Code Review",
            "Engineering Mentorship", "Architecture Review", "Ownership",
        ],
        "default_must_have": [
            "System Design", "Software Architecture", "Backend Architecture",
            "API Design", "Node.js", "Python", "Docker", "Product Engineering",
            "Technical Leadership",
        ],
        "default_core_groups": {
            "architecture_system_design": ["System Design", "Software Architecture", "Backend Architecture", "API Design", "Distributed Systems", "Scalability", "Performance Optimization", "Security", "High-scale Systems"],
            "hands_on_backend": ["Node.js", "Python", "Express", "FastAPI", "Django", "REST API", "SQL", "PostgreSQL", "MongoDB", "Microservices", "Database Design"],
            "devops_delivery": ["Docker", "Kubernetes", "CI/CD", "Git", "GitHub Actions", "AWS", "Azure", "Cloud Architecture", "Deployment"],
            "product_startup_ownership": ["Product Engineering", "Startup Experience", "Product Startup", "0-to-1 Product", "B2B SaaS", "Founder Collaboration", "Ownership"],
            "technical_leadership": ["Technical Leadership", "Code Review", "Engineering Mentorship", "Architecture Review", "Tech Lead", "Mentorship"],
        },
        "default_nice_to_have": [
            "Kubernetes", "AWS", "Azure", "Redis", "Kafka", "Event-driven Architecture",
            "Observability", "Monitoring", "Cost Optimization", "SaaS",
        ],
        "core_groups": {
            "architecture_system_design": ["System Design", "Software Architecture", "Backend Architecture", "API Design", "Distributed Systems", "Scalability", "Performance Optimization", "Security", "High-scale Systems"],
            "hands_on_backend": ["Node.js", "Python", "Express", "FastAPI", "Django", "REST API", "SQL", "PostgreSQL", "MongoDB", "Microservices", "Database Design"],
            "devops_delivery": ["Docker", "Kubernetes", "CI/CD", "Git", "GitHub Actions", "AWS", "Azure", "Cloud Architecture", "Deployment"],
            "product_startup_ownership": ["Product Engineering", "Startup Experience", "Product Startup", "0-to-1 Product", "B2B SaaS", "Founder Collaboration", "Ownership"],
            "technical_leadership": ["Technical Leadership", "Code Review", "Engineering Mentorship", "Architecture Review", "Tech Lead", "Mentorship"],
        },
    },
    "m365_migration_sme": {
        "patterns": [
            r"\bmicrosoft\s+365\s+migration\s+sme\b",
            r"\bm365\s+migration\s+(?:sme|consultant|engineer|specialist)\b",
            r"\boffice\s+365\s+migration\s+(?:engineer|consultant|specialist)\b",
            r"\btenant[-\s]?to[-\s]?tenant\s+migration\s+(?:specialist|engineer|consultant)\b",
            r"\bexchange\s+online\s+migration\s+(?:specialist|engineer|consultant)\b",
            r"\bcollaboration\s+migration\s+engineer\b",
        ],
        "skills": [
            "Microsoft 365 Migration", "Office 365 Migration",
            "Tenant-to-Tenant Migration", "Exchange Online Migration",
            "On-Prem Exchange Migration", "Teams Migration", "SharePoint Migration",
            "OneDrive Migration", "Quest ODM", "PowerShell Scripting",
            "MigrationWiz", "BitTitan", "ShareGate", "AvePoint",
            "Hybrid Exchange", "Mailbox Migration", "Migration Batches",
            "DNS Cutover", "Autodiscover", "MX Records", "Coexistence",
            "Post-migration Validation",
        ],
        "default_must_have": [
            "Microsoft 365 Migration", "Tenant-to-Tenant Migration",
            "Exchange Online Migration", "On-Prem Exchange Migration",
            "Teams Migration", "SharePoint Migration", "OneDrive Migration",
            "Entra ID", "Azure AD", "PowerShell Scripting", "Quest ODM",
        ],
        "default_core_groups": {
            "m365_migration": ["Microsoft 365 Migration", "Office 365 Migration", "Tenant-to-Tenant Migration", "Workload Migration", "Mailbox Migration", "Migration Batches", "Cutover", "Coexistence"],
            "exchange_migration": ["Exchange Online Migration", "On-Prem Exchange Migration", "Exchange Online", "Exchange Server", "Hybrid Exchange", "Mailbox Migration", "EAC", "Exchange PowerShell", "MX Records", "Autodiscover", "SMTP Routing"],
            "workload_migration": ["Teams Migration", "SharePoint Migration", "OneDrive Migration", "Permissions Migration", "Site Migration", "Teams Channels", "Document Library Migration"],
            "tenant_identity": ["Tenant-to-Tenant Migration", "Cross-tenant Migration", "Source Tenant", "Target Tenant", "Domain Move", "Identity Mapping", "Entra ID", "Azure AD", "Azure AD Connect", "Identity Sync"],
            "tools_scripting": ["Quest ODM", "Quest On Demand Migration", "PowerShell Scripting", "MigrationWiz", "BitTitan", "ShareGate", "AvePoint", "Microsoft Graph", "Automation Scripts"],
            "seniority_delivery": ["SME", "Consultant", "Lead", "Senior Engineer", "Enterprise Migration", "Migration Planning", "Cutover Support", "Hypercare", "Post-migration Validation", "US Shift"],
        },
        "default_nice_to_have": [
            "MigrationWiz", "BitTitan", "ShareGate", "AvePoint", "Hybrid Exchange",
            "Mailbox Migration", "DNS Cutover", "MX Records", "Autodiscover",
            "SMTP Routing", "Azure AD Connect", "Conditional Access", "MFA",
            "Microsoft Graph", "Compliance", "Retention", "Hypercare",
        ],
        "core_groups": {
            "m365_migration": ["Microsoft 365 Migration", "Office 365 Migration", "Tenant-to-Tenant Migration", "Workload Migration", "Mailbox Migration", "Migration Batches", "Cutover", "Coexistence"],
            "exchange_migration": ["Exchange Online Migration", "On-Prem Exchange Migration", "Exchange Online", "Exchange Server", "Hybrid Exchange", "Mailbox Migration", "EAC", "Exchange PowerShell", "MX Records", "Autodiscover", "SMTP Routing"],
            "workload_migration": ["Teams Migration", "SharePoint Migration", "OneDrive Migration", "Permissions Migration", "Site Migration", "Teams Channels", "Document Library Migration"],
            "tenant_identity": ["Tenant-to-Tenant Migration", "Cross-tenant Migration", "Source Tenant", "Target Tenant", "Domain Move", "Identity Mapping", "Entra ID", "Azure AD", "Azure AD Connect", "Identity Sync"],
            "tools_scripting": ["Quest ODM", "Quest On Demand Migration", "PowerShell Scripting", "MigrationWiz", "BitTitan", "ShareGate", "AvePoint", "Microsoft Graph", "Automation Scripts"],
            "seniority_delivery": ["SME", "Consultant", "Lead", "Senior Engineer", "Enterprise Migration", "Migration Planning", "Cutover Support", "Hypercare", "Post-migration Validation", "US Shift"],
        },
    },
    "data_science": {
        "patterns": [r"\bdata\s+scientist\b", r"\bstatistical\b", r"\bpredictive\b"],
        "skills": ["Python", "SQL", "Statistics", "Machine Learning", "Pandas", "NumPy"],
        "core_groups": {
            "language": ["Python", "R"],
            "statistics": ["Statistics", "Predictive Analytics"],
            "ml": ["Machine Learning", "Scikit-learn"],
            "data": ["SQL", "Pandas", "NumPy"],
        },
    },
    "business_analyst": {
        "patterns": [
            r"\bbusiness\s+analyst\b",
            r"\bjunior\s+business\s+analyst\b",
            r"\bassociate\s+business\s+analyst\b",
            r"\bbusiness\s+analyst\s+intern\b",
            r"\bfunctional\s+analyst\b",
            r"\bit\s+business\s+analyst\b",
            r"\bbusiness\s+systems?\s+analyst\b",
            r"\brequirements?\s+analyst\b",
            r"\brequirements?\s+gathering\b",
            r"\brequirements?\s+documentation\b",
            r"\bbrd\b|\bfrd\b|\bsrs\b",
            r"\buser\s+stor(?:y|ies)\b",
            r"\buse\s+cases?\b",
            r"\bacceptance\s+criteria\b",
            r"\buat\b|\buser\s+acceptance\s+testing\b",
            r"\bstakeholder\s+(?:management|coordination|meetings?)\b",
        ],
        "skills": [
            "Business Analysis", "Requirement Gathering", "Requirement Analysis",
            "Requirement Documentation", "BRD", "FRD", "SRS", "User Stories",
            "Use Cases", "Acceptance Criteria", "Functional Specification",
            "Stakeholder Management", "UAT", "Change Request", "Gap Analysis",
            "Process Flow", "Workflow Diagram", "Business Process Mapping",
            "Requirement Traceability Matrix", "Agile", "Scrum", "Jira",
            "Confluence", "SQL", "Excel", "Power BI", "Tableau", "Figma",
            "Lucidchart", "MS Visio",
        ],
        "default_must_have": [
            "Business Analysis", "Requirement Gathering", "Requirement Documentation",
            "User Stories", "Use Cases", "Acceptance Criteria",
            "Stakeholder Management", "UAT", "Process Flow",
        ],
        "default_core_groups": {
            "requirements_gathering": ["Requirement Gathering", "Requirement Analysis", "Business Analysis"],
            "requirements_documentation": ["Requirement Documentation", "BRD", "FRD", "SRS", "User Stories", "Use Cases", "Acceptance Criteria", "Functional Specification"],
            "stakeholder_coordination": ["Stakeholder Management", "Communication"],
            "functional_analysis": ["Functional Specification", "Gap Analysis", "Business Process Mapping"],
            "agile_delivery": ["Agile", "Scrum", "Jira", "Confluence", "Backlog Grooming", "Sprint Planning"],
            "uat_change_management": ["UAT", "Change Request", "Test Scenarios", "Defect Clarification"],
            "process_workflow": ["Process Flow", "Workflow Diagram", "Wireframing", "Lucidchart", "Draw.io", "MS Visio", "Figma"],
            "business_data_support": ["SQL", "Excel", "Power BI", "Tableau", "Reporting"],
        },
        "default_nice_to_have": [
            "SQL", "Excel", "Power BI", "Tableau", "Lucidchart", "Draw.io",
            "MS Visio", "Figma", "Balsamiq", "Miro", "CRM", "ERP",
        ],
        "core_groups": {
            "requirements_gathering": ["Requirement Gathering", "Requirement Analysis", "Business Analysis"],
            "requirements_documentation": ["Requirement Documentation", "BRD", "FRD", "SRS", "User Stories", "Use Cases", "Acceptance Criteria", "Functional Specification"],
            "stakeholder_coordination": ["Stakeholder Management", "Communication"],
            "functional_analysis": ["Functional Specification", "Gap Analysis", "Business Process Mapping"],
            "agile_delivery": ["Agile", "Scrum", "Jira", "Confluence", "Backlog Grooming", "Sprint Planning"],
            "uat_change_management": ["UAT", "Change Request", "Test Scenarios", "Defect Clarification"],
            "process_workflow": ["Process Flow", "Workflow Diagram", "Wireframing", "Lucidchart", "Draw.io", "MS Visio", "Figma"],
            "business_data_support": ["SQL", "Excel", "Power BI", "Tableau", "Reporting"],
        },
    },
    "machine_learning": {
        "patterns": [r"\bmachine\s+learning\b", r"\bml\s+engineer\b", r"\bdeep\s+learning\b", r"\bai\s+engineer\b"],
        "skills": ["Python", "Machine Learning", "TensorFlow", "PyTorch", "Scikit-learn", "MLOps"],
        "core_groups": {
            "language": ["Python"],
            "ml_framework": ["TensorFlow", "PyTorch", "Scikit-learn"],
            "mlops": ["MLOps", "Docker", "Kubernetes", "AWS", "Azure"],
        },
    },
    "devops_cloud": {
        "patterns": [r"\bdevops\b", r"\bsre\b", r"\bcloud\s+engineer\b", r"\bplatform\s+engineer\b"],
        "skills": ["AWS", "Azure", "Google Cloud", "Docker", "Kubernetes", "CI/CD", "Terraform", "Linux"],
        "core_groups": {
            "cloud": ["AWS", "Azure", "Google Cloud"],
            "containers": ["Docker", "Kubernetes"],
            "automation": ["CI/CD", "Terraform", "Jenkins", "GitHub Actions"],
            "systems": ["Linux", "Shell Scripting"],
        },
    },
    "cybersecurity": {
        "patterns": [r"\bcyber\s*security\b", r"\bsecurity\s+analyst\b", r"\bsoc\b", r"\bpenetration\b"],
        "skills": ["Cybersecurity", "SIEM", "SOC", "Vulnerability Assessment", "Penetration Testing"],
        "core_groups": {
            "security_ops": ["SOC", "SIEM", "Incident Response"],
            "assessment": ["Vulnerability Assessment", "Penetration Testing"],
        },
    },
    "salesforce_crm": {
        "patterns": [
            r"\bsalesforce\b",
            r"\bsfdc\b",
            r"\bforce\.com\b",
            r"\bapex\b",
            r"\blwc\b",
            r"\blightning\s+web\s+components?\b",
            r"\bvisualforce\b",
            r"\bsalesforce\s+(?:developer|development|engineer|consultant)\b",
        ],
        "skills": [
            "Salesforce",
            "Salesforce Development",
            "Apex",
            "Lightning Web Components",
            "SOQL",
            "Salesforce Flow",
            "Sales Cloud",
            "Service Cloud",
        ],
        "default_must_have": ["Salesforce", "Salesforce Development", "Apex", "SOQL", "Lightning Web Components"],
        "default_core_groups": {
            "platform": ["Salesforce"],
            "programming": ["Apex", "SOQL"],
            "ui": ["Lightning Web Components", "Aura Components", "Visualforce"],
        },
        "default_nice_to_have": [
            "Salesforce Flow",
            "Sales Cloud",
            "Service Cloud",
            "Experience Cloud",
            "Salesforce CPQ",
            "Aura Components",
            "Visualforce",
            "JavaScript",
            "REST API",
            "Salesforce Admin",
            "Data Loader",
            "SFDX",
        ],
        "core_groups": {
            "platform": ["Salesforce"],
            "programming": ["Apex", "SOQL"],
            "ui": ["Lightning Web Components", "Aura Components", "Visualforce"],
            "automation": ["Salesforce Flow", "Process Builder", "Workflow Rules"],
            "cloud": ["Sales Cloud", "Service Cloud", "Experience Cloud"],
        },
    },
    "crm_erp": {
        "patterns": [r"\bcrm\b", r"\berp\b", r"\bsap\b", r"\boracle\b", r"\bhubspot\b"],
        "skills": ["CRM", "ERP", "SAP", "Oracle", "HubSpot", "Salesforce"],
        "core_groups": {
            "platform": ["CRM", "ERP", "SAP", "Oracle", "HubSpot", "Salesforce"],
            "configuration": ["Configuration", "Customization", "Workflow"],
        },
    },
    "hr_recruitment": {
        "patterns": [r"\bhr\b", r"\brecruit(?:er|ment|ing)\b", r"\btalent\s+acquisition\b", r"\bhuman\s+resources\b"],
        "skills": ["Recruitment", "Sourcing", "Screening", "Onboarding", "Payroll", "ATS", "HRMS"],
        "core_groups": {
            "recruitment": ["Recruitment", "Sourcing", "Screening"],
            "hr_ops": ["Onboarding", "Payroll", "Employee Engagement"],
            "tools": ["ATS", "HRMS"],
        },
    },
    "sales_business_development": {
        "patterns": [r"\bsales\b", r"\bbusiness\s+development\b", r"\blead\s+generation\b", r"\baccount\s+executive\b"],
        "skills": ["Lead Generation", "Cold Calling", "Sales Closing", "CRM", "Communication", "Negotiation"],
        "core_groups": {
            "sales": ["Lead Generation", "Cold Calling", "Sales Closing"],
            "crm": ["CRM", "Salesforce", "HubSpot"],
            "communication": ["Communication", "Negotiation"],
        },
    },
    "digital_marketing": {
        "patterns": [r"\bdigital\s+marketing\b", r"\bseo\b", r"\bsem\b", r"\bsocial\s+media\b", r"\bperformance\s+marketing\b"],
        "skills": ["SEO", "SEM", "Google Ads", "Meta Ads", "Social Media Marketing", "Content Marketing", "Analytics"],
        "core_groups": {
            "channels": ["SEO", "SEM", "Social Media Marketing", "Email Marketing"],
            "ads": ["Google Ads", "Meta Ads"],
            "analytics": ["Google Analytics", "Analytics", "Reporting"],
        },
    },
    "finance_accounting": {
        "patterns": [r"\bfinance\b", r"\baccount(?:ant|ing)\b", r"\bfinancial\s+analyst\b", r"\btax\b", r"\baudit\b"],
        "skills": ["Accounting", "Finance", "Tally", "GST", "Tax", "Audit", "Excel", "Financial Analysis"],
        "core_groups": {
            "accounting": ["Accounting", "Tally", "Bookkeeping"],
            "compliance": ["GST", "Tax", "Audit"],
            "analysis": ["Financial Analysis", "Excel"],
        },
    },
    "customer_support": {
        "patterns": [r"\bcustomer\s+support\b", r"\bcustomer\s+service\b", r"\btechnical\s+support\b", r"\bhelpdesk\b"],
        "skills": ["Customer Support", "Customer Service", "Ticketing", "CRM", "Communication", "Troubleshooting"],
        "core_groups": {
            "support": ["Customer Support", "Customer Service", "Troubleshooting"],
            "tools": ["Ticketing", "CRM", "Zendesk", "Freshdesk"],
            "communication": ["Communication"],
        },
    },
    "project_management": {
        "patterns": [r"\bproject\s+manager\b", r"\bprogram\s+manager\b", r"\bscrum\b", r"\bagile\b"],
        "skills": ["Project Management", "Agile", "Scrum", "Jira", "Stakeholder Management"],
        "core_groups": {
            "delivery": ["Project Management", "Program Management"],
            "methodology": ["Agile", "Scrum"],
            "tools": ["Jira", "MS Project"],
        },
    },
    "product_management": {
        "patterns": [r"\bproduct\s+manager\b", r"\bproduct\s+owner\b", r"\broadmap\b", r"\buser\s+stories\b"],
        "skills": ["Product Management", "Roadmap", "User Stories", "Market Research", "Analytics"],
        "core_groups": {
            "product": ["Product Management", "Roadmap", "User Stories"],
            "discovery": ["Market Research", "User Research"],
            "analytics": ["Analytics", "Metrics"],
        },
    },
    "business_analysis": {
        "patterns": [r"\bbusiness\s+analyst\b", r"\brequirements?\s+gathering\b", r"\bbrd\b", r"\bfrd\b"],
        "skills": ["Business Analysis", "Requirements Gathering", "BRD", "FRD", "SQL", "Stakeholder Management"],
        "core_groups": {
            "analysis": ["Business Analysis", "Requirements Gathering"],
            "documentation": ["BRD", "FRD", "User Stories"],
            "data": ["SQL", "Excel"],
        },
    },
    "operations": {
        "patterns": [r"\boperations?\b", r"\bprocess\s+improvement\b", r"\bback\s+office\b"],
        "skills": ["Operations", "Process Improvement", "Excel", "Reporting", "Coordination"],
        "core_groups": {
            "operations": ["Operations", "Process Improvement", "Coordination"],
            "reporting": ["Excel", "Reporting"],
        },
    },
}


FAMILY_ALIASES = set(ROLE_FAMILIES) | {"other"}


def role_family_core_groups(role_family):
    return dict((ROLE_FAMILIES.get(role_family) or {}).get("core_groups") or {})


def role_family_default_must_have(role_family):
    return normalize_skill_list((ROLE_FAMILIES.get(role_family) or {}).get("default_must_have") or [])


def role_family_default_core_groups(role_family):
    return dict((ROLE_FAMILIES.get(role_family) or {}).get("default_core_groups") or {})


def role_family_default_nice_to_have(role_family):
    return normalize_skill_list((ROLE_FAMILIES.get(role_family) or {}).get("default_nice_to_have") or [])


def detect_role_family(text, skills=None):
    combined = f"{text or ''} {' '.join(str(item) for item in skills or [])}".lower()
    best_family = "other"
    best_score = 0

    for family, config in ROLE_FAMILIES.items():
        score = 0
        for pattern in config.get("patterns") or []:
            if re.search(pattern, combined, re.I):
                score += 5
        family_skills = normalize_skill_list(config.get("skills") or [])
        input_skills = normalize_skill_list(skills or [])
        for skill in input_skills:
            if any(skill.lower() == item.lower() or equivalent_skill(skill, item) for item in family_skills):
                score += 3
        if score > best_score:
            best_family = family
            best_score = score

    confidence = min(100, 25 + best_score * 10) if best_score else 20
    return best_family, confidence


def dynamic_core_groups(role_family, jd_skills=None, jd_text=""):
    base_groups = role_family_core_groups(role_family)
    jd_skill_list = normalize_skill_list((jd_skills or []) + known_skills_in_text(jd_text or ""))
    text = f"{jd_text or ''} {' '.join(jd_skill_list)}".lower()
    selected = {}

    for group, options in base_groups.items():
        mentions = []
        for skill in options:
            skill_pattern = re.escape(str(skill).lower()).replace(r"\ ", r"\s+")
            if re.search(r"\b" + skill_pattern + r"\b", text, re.I):
                mentions.append(skill)
        if mentions:
            selected[group] = normalize_skill_list(mentions)

    default_groups = role_family_default_core_groups(role_family)
    explicit_skill_count = len(jd_skill_list)
    if selected and explicit_skill_count >= 3:
        return selected

    if default_groups and len(selected) < 3:
        return default_groups

    if not selected and jd_skill_list:
        selected["jd_required_skills"] = jd_skill_list[:8]

    return selected


def match_core_skill_groups(core_skill_groups, candidate_skills=None, resume_text=""):
    candidate_skills = normalize_skill_list(candidate_skills or [])
    resume_skills = normalize_skill_list(known_skills_in_text(resume_text or ""))
    all_skills = normalize_skill_list(candidate_skills + resume_skills)
    text = (resume_text or "").lower()
    matched = {}
    missing = []

    for group, required_options in (core_skill_groups or {}).items():
        group_hits = []
        for required in normalize_skill_list(required_options or []):
            pattern = re.escape(required.lower()).replace(r"\ ", r"\s+")
            direct_text = bool(re.search(r"\b" + pattern + r"\b", text, re.I))
            skill_hit = any(
                required.lower() == skill.lower() or equivalent_skill(skill, required)
                for skill in all_skills
            )
            if direct_text or skill_hit:
                group_hits.append(required)
        if group_hits:
            matched[group] = normalize_skill_list(group_hits)
        else:
            missing.append(group)

    total = max(len(core_skill_groups or {}), 1)
    percent = round((len(matched) / total) * 100, 2) if core_skill_groups else 0.0
    return {
        "core_skill_match_percent": percent,
        "matched_core_skill_groups": matched,
        "missing_core_skill_groups": missing,
    }
