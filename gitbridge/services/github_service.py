import os
import requests
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

load_dotenv()

class GitHubService:
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token and self.token != "your_github_personal_access_token_here":
            self.headers["Authorization"] = f"token {self.token}"

    def create_repository(self, name: str, description: Optional[str] = None, private: bool = False) -> Dict[str, Any]:
        """Create a new GitHub repository under the authenticated user's account."""
        if not self.token or self.token == "your_github_personal_access_token_here":
            raise ValueError("GitHub Personal Access Token (PAT) is required to create GitHub repositories. Please add your token in Settings & Workspace.")

        url = "https://api.github.com/user/repos"
        payload = {
            "name": name,
            "description": description or f"Repository for {name}",
            "private": private,
            "auto_init": False
        }
        response = requests.post(url, json=payload, headers=self.headers)
        if response.status_code in [200, 201]:
            return response.json()
        else:
            response.raise_for_status()
            return {}

    def fetch_user_repos(self, username: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all public & private repositories across all pages for authenticated user or target username."""
        target_username = username or os.getenv("GITHUB_USERNAME")
        all_repos = []
        page = 1
        
        while True:
            # If authenticated with token, use /user/repos to include private repos
            if self.token and self.token != "your_github_personal_access_token_here":
                url = f"https://api.github.com/user/repos?per_page=100&page={page}&sort=updated&affiliation=owner,collaborator,organization_member"
            elif target_username:
                url = f"https://api.github.com/users/{target_username}/repos?per_page=100&page={page}&sort=updated"
            else:
                url = f"https://api.github.com/user/repos?per_page=100&page={page}&sort=updated"
            
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                if not data:
                    break
                all_repos.extend(data)
                if len(data) < 100:
                    break
                page += 1
            else:
                if page == 1:
                    response.raise_for_status()
                break
        return all_repos

    @staticmethod
    def parse_repo_identifier(repo_input: str) -> str:
        """Extract 'owner/repo' from GitHub URL or 'owner/repo' string."""
        clean = repo_input.strip().rstrip("/")
        if "github.com/" in clean:
            parts = clean.split("github.com/")[-1].split("/")
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
        return clean

    def fetch_repo_details(self, repo_full_name: str) -> Dict[str, Any]:
        """Fetch detailed info for a single repo (e.g. 'owner/repo' or GitHub URL)."""
        clean_name = self.parse_repo_identifier(repo_full_name)
        url = f"https://api.github.com/repos/{clean_name}"
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        else:
            response.raise_for_status()
            return {}

    def fetch_repo_readme(self, repo_full_name: str) -> Optional[str]:
        """Fetch raw content of README.md from repo."""
        clean_name = self.parse_repo_identifier(repo_full_name)
        url = f"https://api.github.com/repos/{clean_name}/readme"
        headers = dict(self.headers)
        headers["Accept"] = "application/vnd.github.v3.raw"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.text
        return None

    def fetch_open_issues(self, repo_full_name: str) -> List[Dict[str, Any]]:
        """Fetch open issues and PRs for a repository."""
        clean_name = self.parse_repo_identifier(repo_full_name)
        url = f"https://api.github.com/repos/{clean_name}/issues?state=open&per_page=30"
        response = requests.get(url, headers=self.headers)
        issues_list = []
        if response.status_code == 200:
            data = response.json()
            for item in data:
                issues_list.append({
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "is_pr": "pull_request" in item,
                    "html_url": item.get("html_url"),
                    "created_at": item.get("created_at"),
                    "user": item.get("user", {}).get("login"),
                    "labels": [l.get("name") for l in item.get("labels", [])]
                })
        return issues_list

    def fetch_recent_commits(self, repo_full_name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch most recent commits for active maintenance tracking."""
        clean_name = self.parse_repo_identifier(repo_full_name)
        url = f"https://api.github.com/repos/{clean_name}/commits?per_page={limit}"
        response = requests.get(url, headers=self.headers)
        commits_list = []
        if response.status_code == 200:
            data = response.json()
            for c in data:
                commit_obj = c.get("commit", {})
                author_obj = commit_obj.get("author", {})
                commits_list.append({
                    "sha": c.get("sha", "")[:7],
                    "message": commit_obj.get("message", "").split("\n")[0],
                    "author": author_obj.get("name") or c.get("author", {}).get("login"),
                    "date": author_obj.get("date")
                })
        return commits_list

    def fetch_dependency_files(self, repo_full_name: str) -> Dict[str, Any]:
        """Inspect repository files to extract package dependencies (package.json, requirements.txt, pyproject.toml)."""
        clean_name = self.parse_repo_identifier(repo_full_name)
        detected_dependencies = []
        file_checks = [
            ("package.json", "Node.js / JS"),
            ("requirements.txt", "Python"),
            ("pyproject.toml", "Python Poetry/Flit"),
            ("Cargo.toml", "Rust"),
            ("go.mod", "Go"),
            ("pom.xml", "Java Maven")
        ]
        
        headers = dict(self.headers)
        headers["Accept"] = "application/vnd.github.v3.raw"

        for filepath, tech_name in file_checks:
            url = f"https://api.github.com/repos/{clean_name}/contents/{filepath}"
            res = requests.get(url, headers=headers)
            if res.status_code == 200:
                detected_dependencies.append(tech_name)
                content = res.text
                if filepath == "package.json":
                    try:
                        import json
                        pkg = json.loads(content)
                        deps = list(pkg.get("dependencies", {}).keys()) + list(pkg.get("devDependencies", {}).keys())
                        detected_dependencies.extend(deps[:15])
                    except Exception:
                        pass
                elif filepath == "requirements.txt":
                    lines = [line.strip().split("==")[0].split(">=")[0] for line in content.splitlines() if line.strip() and not line.startswith("#")]
                    detected_dependencies.extend(lines[:15])

        return {
            "dependencies": list(dict.fromkeys(detected_dependencies))
        }

    def fetch_comprehensive_repo_metadata(self, repo_full_name: str) -> Dict[str, Any]:
        """Fetch complete repository package: details, README, issues, commits, dependencies."""
        clean_name = self.parse_repo_identifier(repo_full_name)
        details = self.fetch_repo_details(clean_name)
        readme = self.fetch_repo_readme(clean_name)
        issues = self.fetch_open_issues(clean_name)
        commits = self.fetch_recent_commits(clean_name, limit=5)
        deps = self.fetch_dependency_files(clean_name)

        tech_stack = self.extract_tech_stack(details)
        if deps.get("dependencies"):
            tech_stack = list(dict.fromkeys(tech_stack + deps["dependencies"]))

        return {
            "details": details,
            "readme": readme,
            "issues": issues,
            "commits": commits,
            "dependencies": deps.get("dependencies", []),
            "tech_stack": tech_stack,
            "last_commit_at": commits[0]["date"] if commits else details.get("pushed_at"),
            "open_issues_count": len(issues)
        }

    def extract_tech_stack(self, repo_data: Dict[str, Any]) -> List[str]:
        """Extract tech stack languages and topics from repo metadata."""
        tech_stack = []
        primary_lang = repo_data.get("language")
        if primary_lang:
            tech_stack.append(primary_lang)
        topics = repo_data.get("topics", [])
        if topics:
            tech_stack.extend(topics)
        return list(dict.fromkeys(tech_stack))

    def parse_repo_to_profile_dict(self, repo_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse raw GitHub API repository metadata into a GitBridge App Profile dict."""
        name = repo_data.get("name", "")
        slug = name.lower().replace(" ", "-").replace("_", "-")
        return {
            "slug": slug,
            "name": name,
            "description": repo_data.get("description") or f"Repository {name}",
            "status": "production" if not repo_data.get("archived") else "archived",
            "github_url": repo_data.get("html_url"),
            "github_repo_name": repo_data.get("full_name"),
            "tech_stack": self.extract_tech_stack(repo_data),
            "tags": repo_data.get("topics", []),
            "version": "0.1.0"
        }
