"""NAS-only data belongs to the project's excluded _private directory."""
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
PRIVATE_DIRECTORY = PROJECT / '_private'


def private_path(path: Path) -> Path:
    requested = Path(path).expanduser().absolute()
    resolved = requested.resolve()
    project = PROJECT.resolve()
    protected = project / '_private'
    inside_private = resolved == protected or protected in resolved.parents
    if resolved == project or (project in resolved.parents and not inside_private):
        raise ValueError('Private data inside the shop must stay in _private')
    # Do not let an internal alias write into public files or outside the project.
    intended_private = (requested == protected or protected in requested.parents or
                        any(parent.resolve() == protected for parent in requested.parents))
    if intended_private and (
            protected.is_symlink() or not inside_private):
        raise ValueError('Private storage must not escape through a symbolic link')
    return resolved
