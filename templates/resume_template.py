"""
HTML resume template for PDF generation.
ATS-friendly, clean single-column layout.
Returns the full HTML string with Jinja2-style placeholders.
"""


import re

def get_resume_html(data: dict) -> str:
    """
    Build a complete HTML resume from the provided data dict.

    Expected data keys:
        name, email, phone, location, summary,
        experience: [{company, role, duration, bullets: [str], certificate_link}],
        projects: [{name, description, bullets: [str], tech: [str], github_link, live_link}],
        skills: {proven: [str], learning: [str]},
        education: [{degree, institution, year}],
        achievements: [str]
    """
    def parse_links(text: str) -> str:
        """Converts Markdown [text](url) to HTML <a> tags and **text** to <strong> tags."""
        if not text:
            return ""
        text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
        return re.sub(
            r'\[([^\]]+)\]\(([^)]+)\)',
            r'<a href="\2" target="_blank" class="inline-link">\1</a>',
            text,
        )

    personal = data.get("personal", data)
    name = personal.get("name", "")
    email = personal.get("email", "")
    phone = personal.get("phone", "")
    location = personal.get("location", "")
    summary = data.get("summary", personal.get("summary", ""))

    # Build Header Links
    links = personal.get("links", {})
    links_html = []
    for platform, url in links.items():
        label = platform.capitalize()
        links_html.append(f'<a href="{url}" target="_blank" class="header-link">{label}</a>')
    header_links_str = " &nbsp;|&nbsp; ".join(links_html)
    if header_links_str:
        header_links_str = f'<div class="contact header-links">{header_links_str}</div>'

    # Build experience section
    exp_entries = []
    for exp in data.get("experience", []):
        bullets_html = "".join(f"<li>{parse_links(b)}</li>" for b in exp.get("bullets", []))

        cert_link = (
            f' <a href="{exp["certificate_link"]}" target="_blank" class="meta-link">[View Certificate]</a>'
            if exp.get("certificate_link")
            else ""
        )

        exp_entries.append(f"""
        <div class="entry">
            <div class="entry-header">
                <span class="entry-title">{exp['role']}</span>
                <span class="entry-date">{exp.get('duration', '')}</span>
            </div>
            <div class="entry-subtitle">{exp['company']}{cert_link}</div>
            <ul>{bullets_html}</ul>
        </div>""")

    exp_html = ""
    if exp_entries:
        exp_html = f'<div style="break-inside: avoid;"><div class="section-title">Experience</div>{exp_entries[0]}</div>' + "".join(exp_entries[1:])

    # Build projects section
    proj_entries = []
    for proj in data.get("projects", []):
        tech_str = ", ".join(proj.get("tech", []))
        desc = parse_links(proj.get("description", ""))
        bullets_html = "".join(f"<li>{parse_links(b)}</li>" for b in proj.get("bullets", []))

        github_link = (
            f' <a href="{proj["github_link"]}" target="_blank" class="meta-link">[GitHub]</a>'
            if proj.get("github_link")
            else ""
        )
        live_link = (
            f' <a href="{proj["live_link"]}" target="_blank" class="meta-link">[Live Demo]</a>'
            if proj.get("live_link")
            else ""
        )

        proj_entries.append(f"""
        <div class="entry">
            <div class="entry-header">
                <span class="entry-title">{proj['name']}</span>
                <span class="entry-links">{github_link}{live_link}</span>
            </div>
            <div class="tech-stack">Tech Stack: {tech_str}</div>
            <div class="project-desc">{desc}</div>
            <ul>{bullets_html}</ul>
        </div>""")

    proj_html = ""
    if proj_entries:
        proj_html = f'<div style="break-inside: avoid;"><div class="section-title">Projects</div>{proj_entries[0]}</div>' + "".join(proj_entries[1:])

    # Build skills section
    skills = data.get("skills", {})
    proven = ", ".join(skills.get("proven", []))
    learning = ", ".join(skills.get("learning", []))
    skills_html = f"<p><strong>Technical Skills:</strong> {proven}</p>"
    if learning:
        skills_html += f"<p><strong>Currently Learning:</strong> {learning}</p>"

    # Build education section
    edu_entries = []
    for edu in data.get("education", []):
        edu_entries.append(f"""
        <div class="entry edu-entry">
            <div class="entry-header">
                <span class="entry-title">{edu['degree']}</span>
                <span class="entry-date">{edu.get('year', '')}</span>
            </div>
            <div class="entry-subtitle">{edu['institution']}</div>
        </div>""")

    edu_html = ""
    if edu_entries:
        edu_html = f'<div style="break-inside: avoid;"><div class="section-title">Education</div>{edu_entries[0]}</div>' + "".join(edu_entries[1:])
    
    # Build extra-curriculars section
    extra_entries = []
    for extra in data.get("extra_curriculars", []):
        bullets_html = "".join(f"<li>{parse_links(b)}</li>" for b in extra.get("bullets", []))
        
        extra_entries.append(f"""
        <div class="entry" style="margin-bottom: 6px;">
            <div style="font-size: 10pt; margin-bottom: 2px;">
                <span class="entry-title">{extra['role']}</span>
                <span style="margin: 0 4px;">|</span>
                <span style="font-style: italic;">{extra['organization']}</span>
            </div>
            <ul>{bullets_html}</ul>
        </div>""")

    extra_html = ""
    if extra_entries:
        extra_html = f'<div style="break-inside: avoid;"><div class="section-title">Leadership & Extra-Curriculars</div>{extra_entries[0]}</div>' + "".join(extra_entries[1:])



    # Build achievements section
    achievements_html = ""
    achievements_list = data.get("achievements", [])
    if achievements_list:
        a = achievements_list[0]
        achievements_html = f"""
    <div class="section">
        <div style="break-inside: avoid;">
            <div class="section-title">Achievements &amp; Publications</div>
            <ul><li>{parse_links(a)}</li>
        </div>"""
        for a in achievements_list[1:]:
            achievements_html += f"<li>{parse_links(a)}</li>"
        achievements_html += "</ul></div>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{name} - Resume</title>
    <style>
        @page {{
            size: A4;
            margin: 1.1cm 1.4cm;
        }}
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Calibri, Arial, sans-serif;
            font-size: 10pt;
            line-height: 1.38;
            color: #000;
        }}

        /* ---------- Header ---------- */
        .header {{
            text-align: center;
            margin-bottom: 10px;
            padding-bottom: 8px;
            border-bottom: 1.5px solid #000;
        }}
        .header h1 {{
            font-size: 18.5pt;
            font-weight: 700;
            color: #000;
            margin-bottom: 4px;
            letter-spacing: 0.4px;
        }}
        .header .contact {{
            font-size: 9pt;
            color: #000;
        }}
        .header .contact span {{
            margin: 0 6px;
        }}
        .header-links {{
            margin-top: 2px;
        }}
        .header-link {{
            color: #2563eb;
            text-decoration: none;
        }}
        .inline-link {{
            color: #2563eb;
            text-decoration: none;
        }}
        .meta-link {{
            font-size: 8.5pt;
            color: #2563eb;
            text-decoration: none;
            font-weight: 600;
            white-space: nowrap;
        }}

        /* ---------- Sections ---------- */
        .section {{
            margin-bottom: 10px;
        }}
        .section:last-child {{
            margin-bottom: 0;
        }}
        .section-title {{
            font-size: 11pt;
            font-weight: 700;
            color: #000;
            text-transform: uppercase;
            letter-spacing: 0.7px;
            border-bottom: 1px solid #000;
            padding-bottom: 2px;
            margin-bottom: 6px;
            break-after: avoid;
            page-break-after: avoid;
        }}

        /* ---------- Generic entry (experience / projects / education) ---------- */
        .entry {{
            margin-bottom: 8px;
        }}
        .entry:last-child {{
            margin-bottom: 0;
        }}
        .entry-header {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            flex-wrap: wrap;
            gap: 2px 10px;
        }}
        .entry-title {{
            font-weight: 700;
            font-size: 10.3pt;
        }}
        .entry-date {{
            font-size: 9pt;
            color: #000;
            white-space: nowrap;
        }}
        .entry-links {{
            font-size: 8.5pt;
            white-space: nowrap;
        }}
        .entry-subtitle {{
            font-size: 9.7pt;
            font-style: italic;
            color: #000;
            margin-top: 1px;
            margin-bottom: 3px;
        }}

        /* ---------- Bullets (experience / projects / achievements) ---------- */
        ul {{
            padding-left: 18px;
            margin-top: 2px;
        }}
        li {{
            margin-bottom: 2px;
            font-size: 9.7pt;
            text-align: justify;
            text-justify: inter-word;
        }}
        li:last-child {{
            margin-bottom: 0;
        }}

        /* ---------- Projects ---------- */
        .tech-stack {{
            font-size: 9pt;
            color: #000;
            margin-bottom: 3px;
            font-style: italic;
        }}
        .project-desc {{
            font-size: 9.7pt;
            margin-top: 2px;
            margin-bottom: 3px;
            text-align: justify;
            text-justify: inter-word;
        }}

        /* ---------- Education ---------- */
        .edu-entry .entry-subtitle {{
            margin-bottom: 0;
        }}

        /* ---------- Summary ---------- */
        .summary {{
            font-size: 9.7pt;
            color: #000;
            text-align: justify;
            text-justify: inter-word;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{name}</h1>
        <div class="contact">
            <span>{email}</span> |
            <span>{phone}</span> |
            <span>{location}</span>
        </div>
        {header_links_str}
    </div>

    <div class="section">
        <div class="section-title" style="break-inside: avoid;">Professional Summary
            <div class="summary" style="font-weight: normal; text-transform: none; font-size: 9.7pt; letter-spacing: normal; padding-top: 5px;">{parse_links(summary)}</div>
        </div>
    </div>

    {f'<div class="section">{exp_html}</div>' if exp_html else ''}

    {f'<div class="section">{proj_html}</div>' if proj_html else ''}

    <div class="section">
        <div style="break-inside: avoid;">
            <div class="section-title">Skills</div>
            {skills_html}
        </div>
    </div>
    {achievements_html}

    {f'<div class="section">{edu_html}</div>' if edu_html else ''}
    {f'<div class="section">{extra_html}</div>' if extra_html else ''}
</body>
</html>"""