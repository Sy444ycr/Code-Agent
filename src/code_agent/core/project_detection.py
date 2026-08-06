from __future__ import annotations

from dataclasses import dataclass

from code_agent.core.workspace import Workspace


@dataclass(frozen=True)
class ProjectEcosystem:
    name: str
    marker: str
    commands: list[str]


class ProjectDetector:
    markers = {
        "pyproject.toml": ("python", ["pytest -q"]),
        "requirements.txt": ("python", ["pytest -q"]),
        "pytest.ini": ("python", ["pytest -q"]),
        "package.json": ("typescript", ["npm test -- --run"]),
        "go.mod": ("go", ["go test ./..."]),
        "pom.xml": ("java", ["mvn test"]),
        "build.gradle": ("java", ["gradle test"]),
        "Cargo.toml": ("rust", ["cargo test"]),
        "CMakeLists.txt": ("cpp", ["cmake --build build", "ctest --test-dir build"]),
        "Makefile": ("make", ["make test"]),
        "composer.json": ("php", ["vendor/bin/phpunit"]),
        "Gemfile": ("ruby", ["bundle exec rspec"]),
    }

    def detect(self, workspace: Workspace) -> list[ProjectEcosystem]:
        found: list[ProjectEcosystem] = []
        for marker, (name, commands) in self.markers.items():
            if (workspace.root / marker).exists():
                found.append(ProjectEcosystem(name=name, marker=marker, commands=commands))
        return found

    def verification_commands(self, workspace: Workspace) -> list[str]:
        commands: list[str] = []
        for ecosystem in self.detect(workspace):
            for command in ecosystem.commands:
                if command not in commands:
                    commands.append(command)
        return commands
