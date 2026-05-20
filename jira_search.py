import json
import os
import gradio as gr
from jira import JIRA, JIRAError

DEFAULT_JIRA_URL = "https://aristocrat.atlassian.net"
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".jira_config.json")


# ─────────────────────────────────────────────
# Credential persistence
# ─────────────────────────────────────────────
def load_credentials():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
            return (
                data.get("jira_url", DEFAULT_JIRA_URL),
                data.get("email", ""),
                data.get("token", ""),
            )
        except Exception:
            pass
    return DEFAULT_JIRA_URL, "", ""


def save_credentials(jira_url, email, token):
    if not all([jira_url.strip(), email.strip(), token.strip()]):
        return "❌ Fill in all fields before saving."
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(
                {"jira_url": jira_url.strip(), "email": email.strip(), "token": token.strip()},
                f, indent=2
            )
        return f"✅ Credentials saved to `{CONFIG_FILE}`"
    except Exception as e:
        return f"❌ Failed to save: {e}"

# ─────────────────────────────────────────────
# Connect to JIRA
# ─────────────────────────────────────────────
def connect_jira(jira_url: str, email: str, credential: str):
    try:
        client = JIRA(server=jira_url.rstrip("/"), basic_auth=(email, credential))
        me = client.myself()
        return client, None, me.get("displayName", email)
    except JIRAError as e:
        return None, f"JIRA Error {e.status_code}: {e.text}", None
    except Exception as e:
        return None, str(e), None


def test_connection(jira_url, email, credential):
    if not all([jira_url.strip(), email.strip(), credential.strip()]):
        return "❌ Fill in all credential fields first."
    client, err, name = connect_jira(jira_url.strip(), email.strip(), credential.strip())
    if err:
        msg = f"❌ {err}\n\n"
        if "401" in str(err):
            msg += (
                "**Troubleshooting 401 tips:**\n"
                "- Use your **Atlassian account email**, not display name\n"
                "- API token must be generated at https://id.atlassian.com/manage-profile/security/api-tokens\n"
                "- Try without `/jira` in the URL (e.g. `https://aristocrat.atlassian.net`)\n"
                "- If org uses **SSO/SAML**, ask IT admin to allow API token access\n"
                "- Some orgs require a **Personal Access Token (PAT)** — check with your admin"
            )
        return msg
    return f"✅ Connected as **{name}**"


# ─────────────────────────────────────────────
# Search JIRA bugs
# ─────────────────────────────────────────────
def search_bugs(jira_url, email, credential, search_text, issue_type, max_results):
    if not email.strip() or not credential.strip():
        return "❌ Please enter your credentials.", ""
    if not search_text.strip():
        return "❌ Please enter a search term.", ""

    client, err, _ = connect_jira(jira_url.strip(), email.strip(), credential.strip())
    if err:
        return f"❌ Connection failed: {err}", ""

    conditions = [
        f'text ~ "{search_text.strip()}"',
        'project in ("NM", "META")',
    ]
    if issue_type != "Any":
        conditions.append(f'issuetype = "{issue_type}"')

    jql = " AND ".join(conditions) + " ORDER BY created DESC"

    try:
        issues = client.search_issues(jql, maxResults=int(max_results))
    except JIRAError as e:
        return f"❌ JQL Error: {e.text}", jql

    if not issues:
        return f"No issues found for: **{search_text}**", jql

    rows = []
    for issue in issues:
        key      = issue.key
        summary  = issue.fields.summary
        status   = issue.fields.status.name
        priority = getattr(issue.fields.priority, "name", "—")
        assignee = getattr(issue.fields.assignee, "displayName", "Unassigned")
        created  = issue.fields.created[:10]
        url      = f"{jira_url.rstrip('/')}/browse/{key}"
        rows.append(f"| [{key}]({url}) | {summary[:60]}{'...' if len(summary)>60 else ''} | {status} | {priority} | {assignee} | {created} |")

    header = "| Key | Summary | Status | Priority | Assignee | Created |\n|---|---|---|---|---|---|"
    table  = header + "\n" + "\n".join(rows)
    return f"✅ **{len(issues)} issue(s)** found for `{search_text}`\n\n{table}", jql


TOKEN_GUIDE = """
### 🔑 How to get a free API Token
1. Go to 👉 [id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **"Create API token"**
3. Give it any label (e.g. `VSCode`) and click **Create**
4. Copy the token and paste it in the field above

> ⚠️ Use your **Atlassian account email** (same as login), not your display name.  
> ⚠️ If your org uses SSO and blocks API tokens, ask IT to enable it.
"""


# ─────────────────────────────────────────────
# Gradio UI
# ─────────────────────────────────────────────
_saved_url, _saved_email, _saved_token = load_credentials()
_has_saved = bool(_saved_email)

with gr.Blocks(title="JIRA Bug Search") as app:
    gr.Markdown("# 🐛 JIRA Bug Search")

    with gr.Row():
        # ── Left: Credentials + Search ───────
        with gr.Column(scale=1):
            gr.Markdown("### 🔑 Credentials")

            if _has_saved:
                gr.Markdown(f"✅ **Saved credentials loaded** for `{_saved_email}`  \n_You can edit below and re-save at any time._")

            jira_url_input = gr.Textbox(
                label="JIRA URL",
                value=_saved_url,
                placeholder="https://yourcompany.atlassian.net"
            )
            email_input = gr.Textbox(
                label="Atlassian Email",
                value=_saved_email,
                placeholder="you@aristocrat.com"
            )
            token_input = gr.Textbox(
                label="API Token or Password",
                value=_saved_token,
                placeholder="Paste token or password here",
                type="password"
            )

            with gr.Row():
                test_btn = gr.Button("🔌 Test Connection", size="sm")
                save_btn = gr.Button("💾 Save Credentials", size="sm")
            conn_status = gr.Markdown(value="")

            with gr.Accordion("📖 How to get a free API Token", open=False):
                gr.Markdown(TOKEN_GUIDE)

            gr.Markdown("### 🔍 Search")
            search_input = gr.Textbox(label="Search text", placeholder="e.g. crash, login, null pointer")
            gr.Markdown("_Searching in projects: **NM**, **META**_")
            issue_type = gr.Dropdown(
                label="Issue type",
                choices=["Any", "Bug", "Task", "Story", "Epic", "Sub-task"],
                value="Bug"
            )
            max_results = gr.Slider(label="Max results", minimum=5, maximum=50, value=10, step=5)
            search_btn  = gr.Button("🔍 Search", variant="primary", size="lg")

        # ── Right: Results ────────────────────
        with gr.Column(scale=2):
            gr.Markdown("### 📋 Search Results")
            results_md  = gr.Markdown(value="_Results will appear here._")
            gr.Markdown("### 📝 JQL Query Used")
            jql_box     = gr.Textbox(label="", interactive=False, lines=2)

    test_btn.click(
        fn=test_connection,
        inputs=[jira_url_input, email_input, token_input],
        outputs=[conn_status]
    )
    save_btn.click(
        fn=save_credentials,
        inputs=[jira_url_input, email_input, token_input],
        outputs=[conn_status]
    )
    search_btn.click(
        fn=search_bugs,
        inputs=[jira_url_input, email_input, token_input, search_input, issue_type, max_results],
        outputs=[results_md, jql_box]
    )
    search_input.submit(
        fn=search_bugs,
        inputs=[jira_url_input, email_input, token_input, search_input, issue_type, max_results],
        outputs=[results_md, jql_box]
    )

if __name__ == "__main__":
    app.launch()
