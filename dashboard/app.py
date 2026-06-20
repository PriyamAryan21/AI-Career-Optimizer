"""
Dashboard — Flask web application.
Serves the management UI for the AI Career Optimizer.
Endpoints:
    /                          → Dashboard home (overview stats)
    /api/trends                → Skill trend data (chart-ready)
    /api/suggestions           → Pending suggestions (approve/reject)
    /api/suggestions/<id>      → Resolve a suggestion
    /api/logs                  → Action log history
    /api/profile               → GET/PUT master_profile.yaml
    /api/resume/generate       → Generate resume from current profile
    /api/resume/jd             → Generate JD-tailored resume
    /api/resume/versions       → List past resume versions
    /api/trigger               → Trigger a manual update cycle
"""

import asyncio
import json
import sys
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import google.generativeai as genai

sys.stdout.reconfigure(encoding='utf-8')

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import (
    load_master_profile, save_master_profile, OUTPUT_DIR,
    GEMINI_API_KEY, GEMINI_MODEL, TARGET_ROLES, BASE_DIR,
    DASHBOARD_USERNAME, DASHBOARD_PASSWORD
)
from database.models import (
    get_action_logs, get_pending_suggestions, resolve_suggestion,
    get_trends_by_role, log_action
)

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# ── Global Security: Basic Auth ────────────────────────
@app.before_request
def require_auth():
    """Enforce HTTP Basic Auth if DASHBOARD_PASSWORD is set."""
    if DASHBOARD_PASSWORD:
        # Exclude health check from auth so Render ping works
        if request.endpoint == 'health_check':
            return
            
        auth = request.authorization
        if not auth or auth.password != DASHBOARD_PASSWORD or auth.username != DASHBOARD_USERNAME:
            return jsonify({"error": "Authentication required"}), 401, {'WWW-Authenticate': 'Basic realm="Login Required"'}

# ── Helper: Run async in sync context ─────────────────
def run_async(coro):
    """Run an async coroutine from synchronous Flask context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Dashboard Home ─────────────────────────────────────
@app.route('/api/health')
def health_check():
    """Lightweight endpoint to keep Render free tier awake."""
    return jsonify({"status": "alive"})

@app.route('/api/metrics')
def api_metrics():
    """Returns historical profile performance metrics for visualization."""
    from database.models import get_profile_metrics
    try:
        metrics = get_profile_metrics()
        return jsonify(metrics)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')


# ── API: Profile (GET / PUT) ──────────────────────────
@app.route('/api/profile', methods=['GET'])
def get_profile():
    """Return the full master_profile.yaml as JSON and sync skills."""
    from database.models import sync_skill_inventory
    try:
        profile = load_master_profile()
        # Automatically sync skills to DB when dashboard overview loads
        try:
            sync_skill_inventory(profile)
        except Exception as sync_e:
            print(f"Warning: Failed to sync skill inventory: {sync_e}")
            
        return jsonify(profile)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/profile', methods=['PUT'])
def update_profile():
    """
    Update the master_profile.yaml.
    Accepts full profile JSON or partial updates.
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        current = load_master_profile()
        
        # Deep merge: update only provided keys
        for key in data:
            if key in current and isinstance(current[key], dict) and isinstance(data[key], dict):
                current[key].update(data[key])
            else:
                current[key] = data[key]
        
        save_master_profile(current)
        log_action("profile_update", "Profile updated via dashboard", status="success")
        return jsonify({"status": "ok", "message": "Profile updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: Skills Management ──────────────────────────────
@app.route('/api/skills', methods=['POST'])
def add_skill():
    try:
        data = request.json
        skill = data.get('skill')
        category = data.get('category', 'learning') # 'proven' or 'learning'
        
        if not skill:
            return jsonify({"error": "Skill name required"}), 400
            
        profile = load_master_profile()
        if 'skills' not in profile:
            profile['skills'] = {'proven': [], 'learning': []}
            
        if skill not in profile['skills'][category]:
            profile['skills'][category].append(skill)
            save_master_profile(profile)
            
            # Sync to DB
            from database.models import sync_skill_inventory
            sync_skill_inventory(profile)
            
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/skills/move', methods=['POST'])
def move_skill():
    """Moves a skill from learning to proven."""
    try:
        data = request.json
        skill = data.get('skill')
        
        profile = load_master_profile()
        if 'learning' in profile.get('skills', {}) and skill in profile['skills']['learning']:
            profile['skills']['learning'].remove(skill)
            if skill not in profile['skills']['proven']:
                profile['skills']['proven'].append(skill)
            save_master_profile(profile)
            
            from database.models import sync_skill_inventory
            sync_skill_inventory(profile)
            
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/skills', methods=['DELETE'])
def remove_skill():
    try:
        data = request.json
        skill = data.get('skill')
        
        profile = load_master_profile()
        removed = False
        if 'learning' in profile.get('skills', {}) and skill in profile['skills']['learning']:
            profile['skills']['learning'].remove(skill)
            removed = True
        if 'proven' in profile.get('skills', {}) and skill in profile['skills']['proven']:
            profile['skills']['proven'].remove(skill)
            removed = True
            
        if removed:
            save_master_profile(profile)
            from database.models import sync_skill_inventory
            sync_skill_inventory(profile)
            
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: Add/Remove Profile Sections ──────────────────
@app.route('/api/profile/project', methods=['POST'])
def add_project():
    """Add a new project to master_profile.yaml."""
    try:
        project = request.get_json()
        profile = load_master_profile()
        
        if "projects" not in profile:
            profile["projects"] = []
        
        # Validate required fields
        if not project.get("name"):
            return jsonify({"error": "Project name is required"}), 400
        
        profile["projects"].append({
            "name": project["name"],
            "description": project.get("description", ""),
            "bullets": project.get("bullets", []),
            "tech": project.get("tech", []),
            "github_link": project.get("github_link", ""),
            "live_link": project.get("live_link", ""),
        })
        
        save_master_profile(profile)
        log_action("profile_update", f"Added project: {project['name']}", status="success")
        return jsonify({"status": "ok", "message": f"Project '{project['name']}' added"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/profile/experience', methods=['POST'])
def add_experience():
    """Add a new experience entry."""
    try:
        exp = request.get_json()
        profile = load_master_profile()
        
        if "experience" not in profile:
            profile["experience"] = []
        
        profile["experience"].append({
            "company": exp.get("company", ""),
            "role": exp.get("role", ""),
            "duration": exp.get("duration", ""),
            "certificate_link": exp.get("certificate_link", ""),
            "bullets": exp.get("bullets", []),
        })
        
        save_master_profile(profile)
        log_action("profile_update", f"Added experience: {exp.get('role', '')} at {exp.get('company', '')}", status="success")
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/profile/achievement', methods=['POST'])
def add_achievement():
    """Add a new achievement."""
    try:
        data = request.get_json()
        profile = load_master_profile()
        
        if "achievements" not in profile:
            profile["achievements"] = []
        
        profile["achievements"].append(data.get("text", ""))
        save_master_profile(profile)
        log_action("profile_update", "Added achievement via dashboard", status="success")
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/api/profile/delete', methods=['POST'])
def delete_profile_item():
    """Delete an item from a profile list."""
    try:
        data = request.get_json()
        item_type = data.get("type")
        index = data.get("index")
        
        profile = load_master_profile()
        if item_type in ["projects", "experience", "achievements", "education", "extra_curriculars"]:
            if 0 <= index < len(profile.get(item_type, [])):
                profile[item_type].pop(index)
        elif item_type.startswith("skills."):
            cat = item_type.split(".")[1]
            if 0 <= index < len(profile.get("skills", {}).get(cat, [])):
                profile["skills"][cat].pop(index)
                
        save_master_profile(profile)
        log_action("profile_update", f"Deleted item from {item_type}", status="success")
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/profile/raw', methods=['GET', 'POST'])
def raw_profile_yaml():
    """Get or update the raw master_profile.yaml content."""
    profile_path = BASE_DIR / "master_profile.yaml"
    if request.method == 'GET':
        try:
            content = profile_path.read_text(encoding="utf-8")
            return jsonify({"status": "ok", "yaml": content})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        try:
            data = request.get_json()
            yaml_content = data.get("yaml", "")
            
            # 1. Validate YAML Syntax
            import yaml
            parsed_data = yaml.safe_load(yaml_content)
            
            # 2. Validate YAML Schema (Structure)
            if not isinstance(parsed_data, dict):
                raise ValueError("YAML must represent a dictionary at the root level.")
            
            # Prevent accidental root-level keys (like typing -hlloe: at the far left)
            allowed_keys = {
                "personal", "headline_pool", "skills", "experience", 
                "projects", "education", "achievements", "certifications", 
                "preferences", "extra_curriculars"
            }
            for key in parsed_data.keys():
                if key not in allowed_keys:
                    raise ValueError(f"Unknown section '{key}' found. Only standard profile sections are allowed.")

            if "personal" not in parsed_data or not isinstance(parsed_data["personal"], dict):
                raise ValueError("Missing or invalid 'personal' section.")
                
            if "name" not in parsed_data["personal"]:
                raise ValueError("'personal' section must contain 'name'.")

            # Ensure lists remain lists AND contain the right type of data
            dict_list_fields = ["experience", "projects", "education", "extra_curriculars"]
            for field in dict_list_fields:
                if field in parsed_data and parsed_data[field] is not None:
                    if not isinstance(parsed_data[field], list):
                        raise ValueError(f"'{field}' must be a list (bullet points).")
                    for item in parsed_data[field]:
                        if not isinstance(item, dict):
                            raise ValueError(f"Every item inside '{field}' must be a structured block, not a plain string.")

            # Achievements is a list of strings
            if "achievements" in parsed_data and parsed_data["achievements"] is not None:
                if not isinstance(parsed_data["achievements"], list):
                    raise ValueError("'achievements' must be a list.")

            # Ensure skills remains a dict
            if "skills" in parsed_data and parsed_data["skills"] is not None:
                if not isinstance(parsed_data["skills"], dict):
                    raise ValueError("'skills' must be a dictionary with categories like 'proven', 'learning'.")

            # 3. Save if perfectly valid
            profile_path.write_text(yaml_content, encoding="utf-8")
            log_action("profile_update", "Updated raw YAML profile", status="success")
            return jsonify({"status": "ok"})
            
        except yaml.YAMLError as e:
            return jsonify({"error": f"YAML Syntax Error: {str(e)}"}), 400
        except ValueError as e:
            return jsonify({"error": f"Schema Validation Error: {str(e)}"}), 400
        except Exception as e:
            return jsonify({"error": f"Unexpected Error: {str(e)}"}), 500



@app.route('/api/profile/smart-add', methods=['POST'])
def smart_add_profile_item():
    """Use Gemini to enhance layman text and add to profile."""
    try:
        data = request.get_json()
        item_type = data.get("type")
        raw_text = data.get("raw_text")
        
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        if item_type == "project":
            prompt = f"""
            You are an expert resume writer. The user built a project and described it in layman's terms:
            "{raw_text}"
            
            1. Write a 1-sentence professional project description.
            2. Convert the details into 3 professional, high-impact resume bullet points using the "Situation, Task, Action, Result (STAR) and Google's XYZ formula (Accomplished [X] as measured by [Y], by doing [Z])" framework.
            3. If specific metrics or numbers are missing, INVENT highly realistic, reasonable numbers.
            4. STRATEGICALLY use **markdown bolding** on the most critical keywords, technologies, and metrics so a recruiter can understand the entire point just by reading the bold text.
            
            Return the output strictly in JSON format matching this structure:
            {{
                "description": "One sentence description with bolded keywords",
                "bullets": ["bullet 1...", "bullet 2..."]
            }}
            """
            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            output = json.loads(response.text)
            description = output.get("description", "A comprehensive software solution.")
            bullets = output.get("bullets", [])
            
            profile = load_master_profile()
            if "projects" not in profile: profile["projects"] = []
            
            # Extract tech
            tech_prompt = f"Extract a comma-separated list of up to 5 core technologies used from this text: {raw_text}. Return ONLY the comma separated list."
            tech_resp = model.generate_content(tech_prompt)
            tech = [t.strip() for t in tech_resp.text.split(',')] if tech_resp.text else []
            
            profile["projects"].append({
                "name": data.get("title", "New Project"),
                "description": description,
                "tech": tech,
                "github_link": data.get("github_link", ""),
                "live_link": data.get("live_link", ""),
                "bullets": bullets
            })
            save_master_profile(profile)
            
        elif item_type == "experience":
            prompt = f"""
            You are an expert resume writer. The user had a job/internship and described it in layman's terms:
            "{raw_text}"
            
            1. Convert this into 3 professional, high-impact resume bullet points using the "Situation, Task, Action, Result (STAR) and Google's XYZ formula (Accomplished [X] as measured by [Y], by doing [Z])" framework.
            2. If specific metrics or numbers are missing, INVENT highly realistic, reasonable numbers.
            3. STRATEGICALLY use **markdown bolding** on the most critical keywords, technologies, and metrics so a recruiter can understand the entire point just by reading the bold text.
            
            Return the output strictly in JSON format matching this structure:
            {{
                "bullets": ["bullet 1...", "bullet 2..."]
            }}
            """
            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            output = json.loads(response.text)
            bullets = output.get("bullets", [])
            
            profile = load_master_profile()
            if "experience" not in profile: profile["experience"] = []
            profile["experience"].append({
                "company": data.get("company", "Company Name"),
                "role": data.get("title", "Software Engineer"),
                "duration": data.get("duration", "2023 - Present"),
                "bullets": bullets
            })
            save_master_profile(profile)
            
        elif item_type == "achievement":
            prompt = f"""
            You are an expert resume writer. Rephrase this layman achievement into a single, highly professional, impact-driven sentence suitable for a top-tier tech resume.
            Layman text: "{raw_text}"
            STRATEGICALLY use **markdown bolding** on the most critical keywords or metrics.
            Return ONLY the final sentence.
            """
            response = model.generate_content(prompt)
            final_text = response.text.strip().strip('- *')
            
            link = data.get("link", "")
            if link:
                final_text += f" [View Certificate/Link]({link})"
                
            profile = load_master_profile()
            if "achievements" not in profile: profile["achievements"] = []
            profile["achievements"].append(final_text)
            save_master_profile(profile)
        
        elif item_type == "extra_curricular":
            prompt = f"""
            You are an expert resume writer. The user held a leadership or extra-curricular role and described what they did in layman's terms:
            "{raw_text}"
            
            1. Convert this into EXACTLY ONE single, highly professional, impact-driven resume bullet point using the "Situation, Task, Action, Result (STAR) and Google's XYZ formula (Accomplished [X] as measured by [Y], by doing [Z])" framework.
            2. If specific metrics or numbers are missing, INVENT highly realistic, reasonable numbers based on the context.
            3. STRATEGICALLY use **markdown bolding** on the most critical keywords, technologies, and metrics so a recruiter can understand the entire point just by reading the bold text.
            
            Return the output strictly in JSON format matching this structure:
            {{
                "bullets": ["single bullet point..."]
            }}
            """
            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            output = json.loads(response.text)
            bullets = output.get("bullets", [])
            
            profile = load_master_profile()
            if "extra_curriculars" not in profile: profile["extra_curriculars"] = []
            profile["extra_curriculars"].append({
                "role": data.get("title", "Member"),
                "organization": data.get("company", "Organization"),
                "bullets": bullets
            })
            save_master_profile(profile)

            
        log_action("profile_update", f"Smart-added {item_type} via AI", status="success")
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: Trend Data ───────────────────────────────────
@app.route('/api/trends')
def get_trends():
    """Return skill trends across all target roles."""
    try:
        all_trends = {}
        for role in TARGET_ROLES:
            trends = get_trends_by_role(role, limit=15)
            all_trends[role] = trends
        return jsonify(all_trends)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: Suggestions ──────────────────────────────────
@app.route('/api/suggestions')
def get_suggestions():
    try:
        suggestions = get_pending_suggestions()
        return jsonify(suggestions)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/suggestions/<int:suggestion_id>', methods=['PUT'])
def update_suggestion(suggestion_id):
    """Approve or reject a suggestion. Body: {"status": "approved"/"rejected"}"""
    try:
        data = request.get_json()
        status = data.get("status", "rejected")
        
        if status not in ("approved", "rejected"):
            return jsonify({"error": "Status must be 'approved' or 'rejected'"}), 400
        
        suggestions = get_pending_suggestions()
        sug = next((s for s in suggestions if s["id"] == suggestion_id), None)
        
        resolve_suggestion(suggestion_id, status)
        
        # If approved, automate the master_profile.yaml update programmatically
        if status == "approved" and sug:
            suggestion_text = sug.get('suggestion_text', '')
            parts = suggestion_text.split(":::")
            target_skill = parts[0].strip() if len(parts) > 1 else None
            
            if target_skill:
                import yaml
                from config.settings import MASTER_PROFILE_PATH
                
                with open(MASTER_PROFILE_PATH, 'r', encoding='utf-8') as f:
                    profile = yaml.safe_load(f)
                    
                stype = sug.get("suggestion_type")
                if stype == "add_skill":
                    if target_skill not in profile["skills"]["learning"] and target_skill not in profile["skills"]["proven"]:
                        profile["skills"]["learning"].append(target_skill)
                    
                    with open(MASTER_PROFILE_PATH, 'w', encoding='utf-8') as f:
                        yaml.dump(profile, f, sort_keys=False, allow_unicode=True, default_flow_style=False)
                    log_action("suggestion_applied", f"Programmatically added: {target_skill}", status="success")
                    from database.models import sync_skill_inventory
                    sync_skill_inventory(profile)
                    
                elif stype == "remove_skill":
                    for cat in ["proven", "learning", "suggested"]:
                        if target_skill in profile["skills"][cat]:
                            profile["skills"][cat].remove(target_skill)
                            
                    with open(MASTER_PROFILE_PATH, 'w', encoding='utf-8') as f:
                        yaml.dump(profile, f, sort_keys=False, allow_unicode=True, default_flow_style=False)
                    log_action("suggestion_applied", f"Programmatically removed: {target_skill}", status="success")
                    from database.models import sync_skill_inventory
                    sync_skill_inventory(profile)
                    
                elif stype == "update_content":
                    import google.generativeai as genai
                    from config.settings import GEMINI_API_KEY, GEMINI_MODEL
                    
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel(GEMINI_MODEL)
                    
                    with open(MASTER_PROFILE_PATH, 'r', encoding='utf-8') as f:
                        current_yaml = f.read()
                        
                    prompt = f"""
                    You are a backend automation tool. Your task is to apply a complex content update to a master_profile.yaml file.
                    
                    SUGGESTION: {sug.get('suggestion_text')}
                    REASONING: {sug.get('ai_reasoning')}
                    
                    CURRENT YAML:
                    {current_yaml}
                    
                    Modify the YAML thoughtfully to incorporate this suggestion (e.g. rewriting a summary, adding a project section, etc.).
                    Return ONLY the valid raw YAML. Do not use markdown code blocks like ```yaml.
                    """
                    
                    response = model.generate_content(prompt)
                    new_yaml = response.text.strip()
                    
                    if new_yaml.startswith("```yaml"): new_yaml = new_yaml[7:]
                    if new_yaml.startswith("```"): new_yaml = new_yaml[3:]
                    if new_yaml.endswith("```"): new_yaml = new_yaml[:-3]
                    new_yaml = new_yaml.strip()
                    
                    yaml.safe_load(new_yaml)
                    
                    with open(MASTER_PROFILE_PATH, 'w', encoding='utf-8') as f:
                        f.write(new_yaml)
                        
                    log_action("suggestion_applied", f"AI applied content update: {target_skill}", status="success")
        
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: Action Logs ──────────────────────────────────
@app.route('/api/logs')
def get_logs():
    try:
        limit = request.args.get('limit', 50, type=int)
        logs = get_action_logs(limit=limit)
        # Convert datetime objects to strings for JSON serialization
        for log in logs:
            for key, value in log.items():
                if isinstance(value, datetime):
                    log[key] = value.isoformat()
        return jsonify(logs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: Resume Generation ────────────────────────────
@app.route('/api/resume/generate', methods=['POST'])
def generate_resume():
    """Generate a resume PDF from current master_profile."""
    try:
        from core.resume_generator import generate_resume_pdf
        pdf_path = generate_resume_pdf()
        filename = Path(pdf_path).name
        return jsonify({"status": "ok", "filename": filename, "path": pdf_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/resume/jd', methods=['POST'])
def generate_jd_resume():
    """
    Generate a JD-tailored resume.
    Body: {"jd": "Full job description text..."}
    Uses Gemini to rewrite profile content to match the specific JD.
    """
    try:
        data = request.get_json()
        jd_text = data.get("jd", "").strip()
        
        if not jd_text or len(jd_text) < 50:
            return jsonify({"error": "Please provide a complete job description (at least 50 characters)"}), 400
        
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        profile = load_master_profile()
        
        # Step 1: Extract key requirements from the JD
        extract_prompt = f"""Analyze this job description and extract:
1. Required skills (list them)
2. Key responsibilities
3. Preferred qualifications
4. Company/role context

JOB DESCRIPTION:
{jd_text}

Return as JSON with keys: required_skills, responsibilities, preferred, context"""

        from config.settings import generate_with_retry
        resp = generate_with_retry(model, extract_prompt)
        
        # Step 2: Rewrite the summary to match JD
        summary_prompt = f"""You are an expert resume writer. Rewrite this candidate's professional summary 
to perfectly match this job description while keeping ALL facts truthful.

CANDIDATE'S CURRENT SUMMARY:
{profile['personal'].get('summary', '')}

CANDIDATE'S SKILLS: {', '.join(profile.get('skills', {}).get('proven', []))}

JOB DESCRIPTION:
{jd_text}

RULES:
- 3-5 sentences, under 500 characters
- Emphasize skills that overlap with the JD requirements
- Do NOT fabricate experience or skills the candidate doesn't have
- Make it ATS-friendly with natural keyword inclusion
- Sound confident and professional
- STRATEGICALLY use **markdown bolding** on the most critical keywords, technologies, and metrics so a recruiter can understand the entire point just by reading the bold text.

Return ONLY the rewritten summary paragraph."""

        summary_resp = generate_with_retry(model, summary_prompt)
        optimized_summary = summary_resp.text.strip().strip('"').strip("'")
        
        # Step 3: Rewrite experience bullets to emphasize JD-relevant work
        optimized_experience = []
        for exp in profile.get("experience", []):
            bullets_text = "\n".join(f"- {b}" for b in exp.get("bullets", []))
            exp_prompt = f"""Rewrite these experience bullets to better match this job description.
Keep ALL metrics, numbers, and facts EXACTLY the same. Only adjust phrasing to emphasize relevant skills.
Use the "Situation, Task, Action, Result (STAR) and Google's XYZ formula" framework.
STRATEGICALLY use **markdown bolding** on the most critical keywords, technologies, and metrics so a recruiter can understand the entire point just by reading the bold text.
JOB DESCRIPTION:
{jd_text}

CURRENT BULLETS:
{bullets_text}

Return ONLY the rewritten bullets as a JSON array of strings."""

            exp_resp = generate_with_retry(model, exp_prompt)
            try:
                # Parse the JSON array from the response
                bullets_text = exp_resp.text.strip()
                # Remove markdown code fences if present
                bullets_text = re.sub(r'^```(?:json)?\s*', '', bullets_text)
                bullets_text = re.sub(r'\s*```$', '', bullets_text)
                rewritten_bullets = json.loads(bullets_text)
                if isinstance(rewritten_bullets, list):
                    optimized_experience.append({"rewritten_bullets": rewritten_bullets})
                else:
                    optimized_experience.append({})
            except (json.JSONDecodeError, Exception):
                optimized_experience.append({})
        
        # Step 4: Rewrite project bullets
        optimized_projects = []
        for proj in profile.get("projects", []):
            bullets_text = "\n".join(f"- {b}" for b in proj.get("bullets", []))
            proj_prompt = f"""Rewrite these project bullets to better match this job description.
Keep ALL metrics and facts EXACTLY the same. Only adjust phrasing.
Use the "Situation, Task, Action, Result (STAR) and Google's XYZ formula" framework.
STRATEGICALLY use **markdown bolding** on the most critical keywords, technologies, and metrics so a recruiter can understand the entire point just by reading the bold text
JOB DESCRIPTION:
{jd_text}

PROJECT: {proj['name']}
CURRENT BULLETS:
{bullets_text}

Return ONLY the rewritten bullets as a JSON array of strings."""

            proj_resp = generate_with_retry(model, proj_prompt)
            try:
                bullets_text = proj_resp.text.strip()
                bullets_text = re.sub(r'^```(?:json)?\s*', '', bullets_text)
                bullets_text = re.sub(r'\s*```$', '', bullets_text)
                rewritten_bullets = json.loads(bullets_text)
                if isinstance(rewritten_bullets, list):
                    optimized_projects.append({"rewritten_bullets": rewritten_bullets})
                else:
                    optimized_projects.append({})
            except (json.JSONDecodeError, Exception):
                optimized_projects.append({})
        
        # Step 5: Generate the PDF with optimized content
        optimized_content = {
            "summary": {"rewritten": optimized_summary},
            "experience": optimized_experience,
            "projects": optimized_projects,
            "keywords_used": [],  # JD keywords
        }
        
        from core.resume_generator import generate_resume_pdf
        pdf_path = generate_resume_pdf(optimized_content)
        filename = Path(pdf_path).name
        
        log_action("jd_resume", f"Generated JD-tailored resume: {filename}", status="success")
        
        return jsonify({
            "status": "ok",
            "filename": filename,
            "path": pdf_path,
            "optimized_summary": optimized_summary
        })
    except Exception as e:
        print(f"⚠️ JD generation failed (API limits?): {e}")
        from core.resume_generator import generate_resume_pdf
        try:
            pdf_path = generate_resume_pdf()
            filename = Path(pdf_path).name
            log_action("jd_resume", f"Fallback to base resume due to AI limit: {e}", status="failed")
            return jsonify({
                "status": "ok",
                "filename": filename,
                "path": pdf_path,
                "optimized_summary": "API rate limit exceeded. Generated standard resume.",
                "message": "AI limits exceeded. Generated base resume instead."
            })
        except Exception as fallback_e:
            return jsonify({"error": f"AI and fallback failed: {fallback_e}"}), 500


@app.route('/api/resume/download/<filename>')
def download_resume(filename):
    """Download a generated resume PDF."""
    try:
        return send_file(OUTPUT_DIR / filename, as_attachment=True)
    except Exception as e:
        return jsonify({"error": f"File not found: {filename}"}), 404


@app.route('/api/resume/versions')
def get_resume_versions():
    """List all generated resume PDFs."""
    try:
        pdfs = sorted(OUTPUT_DIR.glob("*.pdf"), key=lambda x: x.stat().st_mtime, reverse=True)
        versions = []
        for pdf in pdfs[:20]:  # Last 20 resumes
            versions.append({
                "filename": pdf.name,
                "created": datetime.fromtimestamp(pdf.stat().st_mtime).isoformat(),
                "size_kb": round(pdf.stat().st_size / 1024, 1)
            })
        return jsonify(versions)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: Trigger Manual Update Cycle ──────────────────
@app.route('/api/trigger', methods=['POST'])
def trigger_cycle():
    """
    Trigger a full update cycle.
    If GITHUB_TOKEN is set, it triggers the GitHub Actions CI pipeline remotely.
    Otherwise, it falls back to running the cycle in a local background thread.
    """
    github_token = os.getenv("GITHUB_TOKEN")
    github_repo = os.getenv("GITHUB_REPO")  # e.g. "PriyamAryan21/AI-Career-Optimizer"
    
    # Optional mode (full, gaps, jobs, scrape)
    mode = request.json.get("mode", "full") if request.is_json else "full"

    if github_token and github_repo:
        import requests
        url = f"https://api.github.com/repos/{github_repo}/actions/workflows/career-optimizer.yml/dispatches"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {github_token}"
        }
        data = {"ref": "main", "inputs": {"mode": mode}}
        resp = requests.post(url, headers=headers, json=data)
        
        if resp.status_code == 204:
            return jsonify({"status": "ok", "message": f"GitHub Actions triggered remotely (Mode: {mode})"})
        else:
            return jsonify({"error": f"GitHub API failed: {resp.text}"}), 500
            
    else:
        # Local fallback
        if mode == "validate":
            import asyncio
            from core.auth import validate_session
            is_valid = asyncio.run(validate_session())
            if is_valid:
                return jsonify({"status": "ok", "message": "✅ Validation Complete: Session Cookies are ACTIVE and FRESH."})
            else:
                return jsonify({"error": "❌ Validation Complete: Session Cookies are EXPIRED or INVALID."})
                
        def run_cycle():
            import asyncio
            try:
                if mode == "full":
                    from core.freshness_manager import run
                    run()
                elif mode == "scrape":
                    from intelligence.job_feed import fetch_all_api_jobs
                    fetch_all_api_jobs()
                elif mode == "trends":
                    from intelligence.job_feed import fetch_jobs_by_role_api
                    from intelligence.trend_analyzer import analyze_trends
                    analyze_trends(fetch_jobs_by_role_api())
                elif mode == "gaps":
                    from intelligence.gap_analyzer import run_full_analysis
                    run_full_analysis()
                elif mode == "jobs":
                    from intelligence.job_feed import get_hot_job_feed
                    get_hot_job_feed(use_ai_scoring=True)
                elif mode == "push":
                    from core.auth import get_authenticated_context
                    from playwright.async_api import async_playwright
                    from core.headline_rotator import get_next_headline, update_headline_on_naukri
                    from core.resume_generator import upload_resume_to_naukri
                    from config.settings import OUTPUT_DIR, NAUKRI_PROFILE_URL
                    async def push_test():
                        async with async_playwright() as p:
                            browser, context = await get_authenticated_context(p)
                            try:
                                page = await context.new_page()
                                await page.goto(NAUKRI_PROFILE_URL, wait_until="domcontentloaded")
                                new_headline = get_next_headline(use_ai=False)
                                await update_headline_on_naukri(page, new_headline)
                                pdfs = list(OUTPUT_DIR.glob("*.pdf"))
                                if pdfs:
                                    latest_pdf = max(pdfs, key=lambda x: x.stat().st_mtime)
                                    await upload_resume_to_naukri(page, str(latest_pdf))
                            finally:
                                await browser.close()
                    asyncio.run(push_test())
            except Exception as e:
                print(f"Background task {mode} failed: {e}")
        
        thread = threading.Thread(target=run_cycle, daemon=True)
        thread.start()
        return jsonify({"status": "ok", "message": f"Task '{mode}' started locally in background"})

@app.route('/api/session', methods=['POST'])
def update_session():
    """Manually update the session cookies from the dashboard."""
    if not request.is_json:
        return jsonify({"error": "Missing JSON data"}), 400
    
    cookies = request.json.get("cookies", [])
    if not cookies or not isinstance(cookies, list):
        return jsonify({"error": "Invalid cookies format. Must be a JSON array of cookies."}), 400
        
    try:
        from database.models import update_session_status
        cookies_json = json.dumps(cookies)
        update_session_status("active", cookies_json)
        return jsonify({"status": "ok", "message": f"Successfully saved {len(cookies)} cookies to Supabase!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/schedule/next')
def get_next_schedule():
    """Calculate the next scheduled run based on the last successful cycle."""
    try:
        from database.models import _get_connection
        conn = _get_connection()
        cur = conn.cursor()
        cur.execute("SELECT created_at FROM action_logs WHERE action_type = 'update_cycle' AND status = 'success' ORDER BY created_at DESC LIMIT 1")
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        from config.settings import UPDATE_FREQUENCY_DAYS
        from datetime import timedelta
        
        if row and row[0]:
            last_run = row[0]
            next_run = last_run + timedelta(days=UPDATE_FREQUENCY_DAYS)
            return jsonify({"next_run": next_run.isoformat() + "Z"})
        else:
            return jsonify({"next_run": None})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── API: Hot Job Feed ─────────────────────────────────
@app.route('/api/jobs')
def get_hot_jobs():
    """
    Return the hot job feed aggregated from the database.
    Query params:
        ?refresh=true — Force refresh the feed via API & Gemini (Warning: takes ~30-40s)
    """
    try:
        refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        if refresh:
            # Triggers the scraper, AI scoring, and saves new Top 10 to DB
            from intelligence.job_feed import get_hot_job_feed
            get_hot_job_feed(use_ai_scoring=True)
            
        # Read instantly from the database
        from database.models import _get_connection
        conn = _get_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT * FROM hot_jobs ORDER BY match_score DESC, id ASC")
        columns = [desc[0] for desc in cur.description]
        
        jobs = []
        for row in cur.fetchall():
            job_dict = dict(zip(columns, row))
            # Convert comma-separated string back to list for the frontend
            if job_dict.get("skills"):
                job_dict["skills"] = job_dict["skills"].split(",")
            else:
                job_dict["skills"] = []
            jobs.append(job_dict)
            
        cur.close()
        conn.close()
        
        return jsonify(jobs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/jobs/sources')
def get_job_sources():
    """Return which job sources are configured and available."""
    return jsonify({
        "remotive": {"active": True, "note": "No API key needed"},
        "adzuna": {
            "active": bool(os.getenv("ADZUNA_APP_ID")),
            "note": "Register free at https://developer.adzuna.com/"
        },
        "jsearch": {
            "active": bool(os.getenv("RAPIDAPI_KEY")),
            "note": "Register free at https://rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch (200/mo)"
        },
        "naukri": {"active": True, "note": "Uses cached scraper data"},
    })


# ── Run ───────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    if '--dev' in sys.argv:
        # Development mode: Flask's built-in server with debug output
        print("🔧 Running in DEVELOPMENT mode (Flask debug server)")
        app.run(debug=True, use_reloader=False, port=5000)
    else:
        # Production mode: Waitress WSGI server
        from waitress import serve
        print("🚀 Running in PRODUCTION mode (Waitress)")
        print("   Dashboard: http://localhost:5000")
        serve(app, host='0.0.0.0', port=5000, threads=4)

