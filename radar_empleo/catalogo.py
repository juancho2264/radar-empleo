"""
Catálogo de tecnologías y las distintas formas en que aparecen escritas en los avisos.

Cada entrada es: nombre canónico → variantes (en minúsculas y sin tildes).

REGLA IMPORTANTE: solo se agrupan nombres que significan LO MISMO ("Postgres" = "PostgreSQL").
Herramientas parecidas pero distintas van separadas (Maven ≠ Gradle, Jenkins ≠ GitHub Actions):
si las juntáramos, el radar diría que sabés algo que no usaste y te sugeriría ponerlo en el CV.
"""

TECNOLOGIAS: dict[str, list[str]] = {
    # Backend
    "java": ["java", "java 8", "java 11", "java 17", "java 21", "java se", "java ee", "jakarta ee", "j2ee"],
    "spring boot": ["spring boot", "springboot", "spring framework", "spring"],
    "spring security": ["spring security"],
    "jpa": ["jpa", "spring data", "spring data jpa", "hibernate"],  # Spring Data JPA usa Hibernate por dentro
    "jwt": ["jwt", "json web token", "json web tokens"],
    "api rest": ["api rest", "apis rest", "rest api", "rest apis", "restful", "api restful", "servicios rest", "servicios web rest"],
    "microservicios": ["microservicios", "microservices"],
    "python": ["python", "python3", "python 3"],
    "django": ["django"],
    "flask": ["flask"],
    "fastapi": ["fastapi"],
    "node": ["node", "nodejs", "node.js"],
    "express": ["express", "expressjs", "express.js"],
    "nestjs": ["nestjs", "nest.js"],
    "c#": ["c#", "csharp"],
    ".net": [".net", "dotnet", "asp.net", ".net core"],
    "php": ["php"],
    "laravel": ["laravel"],
    "go": ["golang"],
    "kotlin": ["kotlin"],
    # Frontend
    "javascript": ["javascript", "js", "ecmascript", "es6", "vanilla js"],
    "typescript": ["typescript"],
    "react": ["react", "reactjs", "react.js"],
    "next.js": ["next.js", "nextjs"],
    "angular": ["angular"],
    "vue": ["vue", "vuejs", "vue.js"],
    "html": ["html", "html5"],
    "css": ["css", "css3"],
    "sass": ["sass", "scss"],
    "tailwind": ["tailwind", "tailwindcss", "tailwind css"],
    # Datos
    "sql": ["sql"],
    "mysql": ["mysql", "mariadb"],
    "postgresql": ["postgresql", "postgres"],
    "sql server": ["sql server", "mssql", "t-sql"],
    "oracle": ["oracle", "pl/sql"],
    "mongodb": ["mongodb", "mongo"],
    "redis": ["redis"],
    # Testing
    "junit": ["junit", "junit5", "junit 5"],
    "mockito": ["mockito"],
    "testing": ["testing", "tests unitarios", "test unitarios", "unit testing", "unit tests", "pruebas unitarias", "tests automatizados"],
    "tdd": ["tdd"],
    "playwright": ["playwright"],
    "selenium": ["selenium"],
    "cypress": ["cypress"],
    # Herramientas y cloud
    "git": ["git"],
    "github": ["github"],
    "gitlab": ["gitlab"],
    "github actions": ["github actions"],
    "ci/cd": ["ci/cd", "ci cd", "integracion continua", "continuous integration"],
    "jenkins": ["jenkins"],
    "docker": ["docker", "contenedores docker"],
    "kubernetes": ["kubernetes", "k8s"],
    "maven": ["maven"],
    "gradle": ["gradle"],
    "aws": ["aws", "amazon web services"],
    "azure": ["azure"],
    "google cloud": ["google cloud", "gcp", "google cloud platform"],
    "linux": ["linux"],
    "scrum": ["scrum", "metodologias agiles", "agile"],
    "jira": ["jira"],
}

# Palabras que indican el nivel que piden.
NIVELES: dict[str, list[str]] = {
    "trainee": ["trainee", "pasante", "pasantia", "practicante", "intern", "internship"],
    "junior": ["junior", "jr", "jr.", "sin experiencia", "primer empleo", "entry level", "entry-level"],
    "semi senior": ["semi senior", "semisenior", "semi-senior", "ssr", "ssr.", "mid level", "mid-level", "middle", "mid"],
    # Ojo: no poner "lead" ni "staff" solos: aparecen en "leading company" o "staff augmentation"
    "senior": ["senior", "sr", "sr.", "tech lead", "team lead", "lead developer", "lider tecnico", "arquitecto"],
}
