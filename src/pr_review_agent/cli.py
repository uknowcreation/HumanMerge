from __future__ import annotations

from pathlib import Path
from typing import Optional, Protocol, Sequence, Tuple

from pr_review_agent.backends import AnalysisBackend, BackendError, default_backends
from pr_review_agent.config import AgentConfig
from pr_review_agent.github import GhGitHubClient, GitHubClient, GitHubError, aggregate_metadata


RESET = "\033[0m"
BOLD = "\033[1m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MUTED = "\033[2m"
CUSTOM_LABEL = "__custom_label__"
CUSTOM_LANGUAGE = "__custom_language__"

Choice = Tuple[str, str]
MultiChoice = Tuple[str, str, bool]


class Prompter(Protocol):
    def select(self, message: str, choices: Sequence[Choice]) -> str:
        ...

    def checkbox(self, message: str, choices: Sequence[MultiChoice]) -> tuple[str, ...]:
        ...

    def text(self, message: str, default: str) -> str:
        ...


class QuestionaryPrompter:
    def __init__(self) -> None:
        try:
            import questionary
        except ImportError as error:
            raise RuntimeError(
                "La dépendance 'questionary' manque. Lancez `uv sync` ou "
                "`python -m pip install -e .`."
            ) from error
        self._questionary = questionary
        self._style = questionary.Style(
            [
                ("qmark", "fg:#22d3ee bold"),
                ("question", "bold"),
                ("answer", "fg:#22c55e bold"),
                ("pointer", "fg:#22d3ee bold"),
                ("highlighted", "fg:#22d3ee bold"),
                ("selected", "fg:#22c55e"),
                ("instruction", "fg:#6b7280 italic"),
                ("text", "fg:#f8fafc"),
                ("disabled", "fg:#6b7280 italic"),
            ]
        )

    def select(self, message: str, choices: Sequence[Choice]) -> str:
        rendered = [self._questionary.Choice(title=title, value=value) for title, value in choices]
        answer = self._questionary.select(
            message,
            choices=rendered,
            pointer="❯",
            qmark="◆",
            instruction="(↑/↓ pour naviguer, Entrée pour valider)",
            style=self._style,
        ).ask()
        if answer is None:
            raise KeyboardInterrupt
        return str(answer)

    def checkbox(self, message: str, choices: Sequence[MultiChoice]) -> tuple[str, ...]:
        rendered = [
            self._questionary.Choice(title=title, value=value, checked=checked)
            for title, value, checked in choices
        ]
        answer = self._questionary.checkbox(
            message,
            choices=rendered,
            pointer="❯",
            qmark="◆",
            instruction="(↑/↓ pour naviguer, Espace pour cocher, Entrée pour valider)",
            validate=lambda selected: bool(selected)
            or "Cochez au moins un élément avec la touche Espace.",
            style=self._style,
        ).ask()
        if answer is None:
            raise KeyboardInterrupt
        return tuple(str(item) for item in answer)

    def text(self, message: str, default: str) -> str:
        answer = self._questionary.text(
            message,
            default=default,
            qmark="◆",
            style=self._style,
        ).ask()
        if answer is None:
            raise KeyboardInterrupt
        cleaned = str(answer).strip()
        return cleaned or default


def _title() -> None:
    print(f"{CYAN}{BOLD}╭──────────────────────────────────────────╮{RESET}")
    print(f"{CYAN}{BOLD}│       ✦ PR Review Agent · setup          │{RESET}")
    print(f"{CYAN}{BOLD}╰──────────────────────────────────────────╯{RESET}\n")


def _connect_github(prompter: Prompter, github: GitHubClient) -> tuple[str, tuple[str, ...]]:
    if not github.is_available():
        raise RuntimeError("GitHub CLI (`gh`) est requis. Installez-le puis relancez la commande.")

    if not github.is_authenticated():
        action = prompter.select(
            "GitHub n'est pas connecté",
            (
                ("Se connecter à GitHub maintenant", "login"),
                ("Quitter la configuration", "quit"),
            ),
        )
        if action == "quit":
            raise KeyboardInterrupt
        print(f"{CYAN}◆ Ouverture de GitHub dans votre navigateur…{RESET}")
        if not github.login():
            raise RuntimeError("La connexion GitHub a échoué ou a été annulée.")

    user = github.current_user()
    print(f"{GREEN}{BOLD}◆ GitHub connecté : {user}{RESET}")

    organizations = tuple(github.organizations())
    owner_choices = [(f"Compte personnel · {user}", user)]
    owner_choices.extend(
        (f"Organisation · {organization}", organization) for organization in organizations
    )
    owner = prompter.select("Quel espace GitHub configurer ?", tuple(owner_choices))

    available_repositories = tuple(github.repositories(owner))
    if not available_repositories:
        raise RuntimeError(f"Aucun dépôt accessible trouvé pour {owner}.")
    preselect_single_repository = len(available_repositories) == 1
    repository_choices = tuple(
        (repository, repository, preselect_single_repository)
        for repository in available_repositories
    )
    repositories: tuple[str, ...] = ()
    while not repositories:
        repositories = prompter.checkbox(
            "Quels dépôts surveiller ? · Espace pour cocher",
            repository_choices,
        )
        if not repositories:
            print(
                f"{YELLOW}◆ Aucun dépôt coché. Placez le curseur sur un dépôt, "
                f"appuyez sur Espace, puis sur Entrée.{RESET}"
            )
    return user, repositories


def _choose_languages(
    prompter: Prompter,
    detected: Sequence[str],
    reviewer: str,
) -> tuple[str, ...]:
    if not detected:
        default = "typescript" if reviewer == "frontend" else "python"
        raw = prompter.text("Langages principaux, séparés par des virgules", default)
        return tuple(item.strip().lower() for item in raw.split(",") if item.strip())

    selected = prompter.checkbox(
        "Langages principaux détectés",
        tuple((language, language, True) for language in detected)
        + (("✎ Ajouter des langages manuellement…", CUSTOM_LANGUAGE, False),),
    )
    languages = [item for item in selected if item != CUSTOM_LANGUAGE]
    if CUSTOM_LANGUAGE in selected:
        raw = prompter.text("Langages supplémentaires, séparés par des virgules", "")
        languages.extend(item.strip().lower() for item in raw.split(",") if item.strip())
    if not languages:
        raise RuntimeError("Sélectionnez au moins un langage.")
    return tuple(dict.fromkeys(languages))


def _choose_label(
    prompter: Prompter,
    kind: str,
    suggested: str,
    available: Sequence[str],
) -> str:
    ordered = []
    matching = next(
        (label for label in available if label.casefold() == suggested.casefold()), None
    )
    if matching:
        ordered.append((f"{matching} (recommandé)", matching))
    else:
        ordered.append((f"{suggested} (nouveau label recommandé)", suggested))
    ordered.extend((label, label) for label in available if label != matching)
    ordered.append(("✎ Écrire un label personnalisé…", CUSTOM_LABEL))
    selected = prompter.select(
        f"Quel label GitHub déclenche le reviewer {kind} ?",
        tuple(ordered),
    )
    if selected == CUSTOM_LABEL:
        return prompter.text(f"Votre label {kind}", suggested)
    return selected


def _choose_analysis_backend(
    prompter: Prompter,
    backends: Sequence[AnalysisBackend],
) -> tuple[str, str]:
    by_id = {backend.id: backend for backend in backends}
    selected = prompter.select(
        "Comment souhaitez-vous exécuter les reviews ?",
        tuple((backend.display_name, backend.id) for backend in backends),
    )
    backend = by_id[selected]

    if not backend.is_available():
        raise RuntimeError(
            f"{backend.display_name} n'est pas installé ou n'est pas accessible dans le terminal."
        )

    if not backend.is_authenticated():
        if backend.auth_kind == "environment":
            credential = getattr(backend, "credential_name", "la variable attendue")
            subject = "Les variables" if " et " in credential else "La variable"
            state = "sont absentes" if " et " in credential else "est absente"
            pronoun = "Ajoutez-les" if " et " in credential else "Ajoutez-la"
            raise RuntimeError(
                f"{subject} {credential} {state}. {pronoun} à votre environnement "
                "(et plus tard aux secrets GitHub), puis relancez la configuration."
            )
        action = prompter.select(
            f"{backend.display_name} n'est pas connecté",
            (
                ("Se connecter maintenant", "login"),
                ("Quitter la configuration", "quit"),
            ),
        )
        if action == "quit":
            raise KeyboardInterrupt
        print(f"{CYAN}◆ Ouverture de la connexion dans votre navigateur…{RESET}")
        if not backend.authenticate():
            raise RuntimeError(
                f"La connexion à {backend.display_name} a échoué ou a été annulée."
            )

    print(f"{CYAN}◆ Recherche des modèles disponibles…{RESET}")
    models = tuple(backend.list_models())
    if not models:
        raise RuntimeError(
            f"Aucun modèle disponible n'a été trouvé pour {backend.display_name}."
        )
    ordered = tuple(
        sorted(models, key=lambda item: (not item.is_default, item.display_name.casefold()))
    )
    model = prompter.select(
        "Quel modèle utiliser ?",
        tuple((option.menu_title, option.id) for option in ordered),
    )
    return backend.id, model


def collect_config(
    prompter: Prompter,
    github: GitHubClient,
    backends: Optional[Sequence[AnalysisBackend]] = None,
) -> AgentConfig:
    github_user, repositories = _connect_github(prompter, github)
    print(f"{CYAN}◆ Analyse des langages et labels des dépôts sélectionnés…{RESET}")
    metadata = aggregate_metadata(github, repositories)

    reviewer = prompter.select(
        "Quel reviewer configurer ?",
        (
            ("Frontend", "frontend"),
            ("Backend", "backend"),
            ("Automatique selon les labels", "auto"),
        ),
    )
    languages = _choose_languages(prompter, metadata.languages, reviewer)

    frontend_label: Optional[str] = None
    backend_label: Optional[str] = None
    if reviewer in {"frontend", "auto"}:
        frontend_label = _choose_label(prompter, "frontend", "front-end", metadata.labels)
    if reviewer in {"backend", "auto"}:
        backend_label = _choose_label(prompter, "backend", "back-end", metadata.labels)

    analysis_backend, model = _choose_analysis_backend(
        prompter,
        tuple(backends) if backends is not None else default_backends(),
    )
    output_language = prompter.text("Langue des commentaires", "fr")

    return AgentConfig(
        github_user=github_user,
        repositories=repositories,
        reviewer=reviewer,
        frontend_label=frontend_label,
        backend_label=backend_label,
        languages=languages,
        analysis_backend=analysis_backend,
        model=model,
        output_language=output_language,
    )


def run_setup(
    destination: Path,
    prompter: Optional[Prompter] = None,
    github: Optional[GitHubClient] = None,
    backends: Optional[Sequence[AnalysisBackend]] = None,
) -> Path:
    _title()
    active_prompter = prompter or QuestionaryPrompter()
    active_github = github or GhGitHubClient()
    config = collect_config(active_prompter, active_github, backends)
    config.write(destination)
    print(f"\n{GREEN}{BOLD}◆ Configuration créée : {destination}{RESET}")
    print(f"  {GREEN}●{RESET} Exécution : {config.analysis_backend} · {config.model}")
    print(f"  {YELLOW}●{RESET} Publication automatique : désactivée")
    print(f"  {GREEN}●{RESET} Validation humaine : obligatoire")
    return destination


def main() -> None:
    try:
        run_setup(Path(".pr-review-agent.yml"))
    except (KeyboardInterrupt, EOFError):
        print(f"\n{MUTED}Configuration annulée.{RESET}")
    except (BackendError, GitHubError, RuntimeError) as error:
        print(f"\n{RED}{BOLD}◆ Erreur : {error}{RESET}")
