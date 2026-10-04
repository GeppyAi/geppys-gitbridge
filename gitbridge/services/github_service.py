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
        url = f"https://api.github.com/repos/{repo_full_name}/readme"
        headers = dict(self.headers)
        headers["Accept"] = "application/vnd.github.v3.raw"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.text
        return None

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
