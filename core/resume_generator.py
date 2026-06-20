"""
Resume generator — builds keyword-optimized PDF resumes.
Merges master_profile data with AI-rewritten content from keyword_injector,
generates a PDF via WeasyPrint, and uploads it to Naukri.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from config.settings import load_master_profile, OUTPUT_DIR
from playwright.sync_api import sync_playwright
import tempfile
import os
from templates.resume_template import get_resume_html
from database.models import save_resume_version, log_action


def _merge_optimized_content(profile: dict, optimized: dict) -> dict:
    """
    Merge AI-rewritten content into the profile data for resume generation.
    If no optimized content, returns profile as-is.
    """
    if not optimized:
        return profile

    merged = dict(profile)  # Shallow copy

    # Replace summary with rewritten version
    if "summary" in optimized and optimized["summary"].get("rewritten"):
        merged["summary"] = optimized["summary"]["rewritten"]
    else:
        merged["summary"] = profile["personal"].get("summary", "")

    # Replace experience bullets
    if "experience" in optimized:
        merged_exp = []
        for i, exp in enumerate(profile.get("experience", [])):
            entry = dict(exp)
            if i < len(optimized["experience"]):
                opt_exp = optimized["experience"][i]
                if opt_exp.get("rewritten_bullets"):
                    entry["bullets"] = opt_exp["rewritten_bullets"]
            merged_exp.append(entry)
        merged["experience"] = merged_exp

    # Replace project descriptions
        # Replace project bullets
    if "projects" in optimized:
        merged_proj = []
        for i, proj in enumerate(profile.get("projects", [])):
            entry = dict(proj)
            if i < len(optimized["projects"]):
                opt_proj = optimized["projects"][i]
                if opt_proj.get("rewritten_bullets"):
                    entry["bullets"] = opt_proj["rewritten_bullets"]
            merged_proj.append(entry)
        merged["projects"] = merged_proj

    return merged


def generate_resume_pdf(optimized_content: dict = None) -> str:
    """
    Generate a keyword-optimized PDF resume.

    Args:
        optimized_content: Output from keyword_injector.generate_optimized_content().
                           If None, uses raw master_profile data.

    Returns:
        Path to the generated PDF file.
    """
    profile = load_master_profile()
    data = _merge_optimized_content(profile, optimized_content)

    # Ensure personal data is accessible at top level
    data["personal"] = profile["personal"]
    if "summary" not in data:
        data["summary"] = profile["personal"].get("summary", "")

    # Generate HTML
    html_content = get_resume_html(data)

    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"resume_{timestamp}.pdf"
    output_path = OUTPUT_DIR / filename

    # Generate PDF
    # Generate PDF using Playwright (No GTK dependency!)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    from playwright.sync_api import sync_playwright
    import tempfile
    import os
    
    # Save HTML to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as f:
        f.write(html_content)
        temp_file = f.name
        
    try:
        # Open the HTML file in headless Chrome and print to PDF
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # Convert Windows path to file URI
            file_url = "file:///" + temp_file.replace("\\", "/")
            page.goto(file_url, wait_until="networkidle")
            page.pdf(path=str(output_path), format="A4", print_background=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
            browser.close()
    finally:
        # Clean up temp file
        if os.path.exists(temp_file):
            os.unlink(temp_file)


    # Log to database
    keywords = optimized_content.get("keywords_used", []) if optimized_content else []
    save_resume_version(
        file_path=str(output_path),
        keywords_used=keywords,
        changes_summary=f"Generated with {len(keywords)} trending keywords"
    )

    log_action(
        "resume_generation",
        f"Generated resume: {filename}",
        details=f"Keywords: {', '.join(keywords[:10])}"
    )

    print(f"   Resume saved: {output_path}")
    return str(output_path)


async def upload_resume_to_naukri(page, pdf_path: str) -> bool:
    """
    Upload the generated PDF to Naukri profile.
    Assumes page is already authenticated and on the profile page.
    """
    try:
        # Simply look for the first file input on the page
        file_input = page.locator("input[type='file']").first
        
        # Sometimes the input is hidden, so we use force=True or javascript to click/set
        await file_input.set_input_files(pdf_path, timeout=10000)

        # If there's a visible "Update Resume" button, click it first
        update_btn = page.locator(
            "button:has-text('Update Resume'), a:has-text('Update Resume'), "
            "div:has-text('Update Resume') >> xpath=.., "
            "label:has-text('Update Resume')"
        ).first

        try:
            await update_btn.click(timeout=3000)
            await page.wait_for_timeout(1000)
        except Exception:
            pass  # May not need a button click if file input is already visible

        # Check for success indicators
        print(f"   Resume uploaded to Naukri: {Path(pdf_path).name}")
        log_action(
            "resume_upload",
            f"Uploaded resume to Naukri",
            details=pdf_path,
            status="success"
        )
        return True

    except Exception as e:
        print(f"   Resume upload failed: {e}")
        log_action("resume_upload", f"Failed: {e}", status="failed")
        return False


# ── CLI ────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')

    print("Generating resume PDF (without AI optimization)...")
    path = asyncio.run(generate_resume_pdf())
    print(f"Done! File: {path}")
