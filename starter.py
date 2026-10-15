"""Local, dependency-free starter. No network, subprocess, or background workers."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import stat
import sys

VERSION = "0.2.0-rc.6"
BASE = Path(__file__).absolute().parent
STATE = ".starter-state.json"
CORE = ["FIRST_USE.md", "AGENTS.md", ".gitignore", "workspace/README.md", "personal/README.md", "private/overlay.md", "task.md"]
RECOVERY = ["recovery/checkpoint.md"]
RECOMMENDED = ["profile/style.md"] + ["standards/" + name + ".md" for name in
    ("task-flow", "storage", "research-evidence", "change-recovery", "tool-adoption", "closeout")]
PRIVATE = ["private/overlay.md", "private/profile.md"]
PROFILE_SCHEMA = "harness-private-profile"
MAX_PROFILE_BYTES = 262144
MAX_TEXT_BYTES = 65536
DEMO = {"example/input.json": b'{"items": [2, 3, 5]}\n', "example/result.json": b'{"count": 3, "total": 10}\n'}


class Refusal(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def validate_path_text(value):
    """Reject device/alias syntax before any filesystem access, on every OS.

    Portable file names intentionally follow Windows restrictions even on POSIX.
    Ordinary absolute POSIX paths and directory-navigation components still work.
    """
    raw = os.fspath(value)
    if not isinstance(raw, str) or not raw:
        raise Refusal("Invalid path text")
    normalized = raw.replace("\\", "/")
    if normalized.startswith(("//./", "//?/", "/??/")):
        raise Refusal("Device namespaces are not supported")
    for index, component in enumerate(normalized.split("/")):
        if not component or component in (".", ".."):
            continue
        if index == 0 and len(component) == 2 and component[0].isascii() and component[0].isalpha() and component[1] == ":" and normalized.startswith(component + "/"):
            continue  # Only an absolute drive anchor can contain a colon.
        if (component.endswith((".", " "))
                or any(ord(char) < 32 or ord(char) == 127 or char in ':<>"|?*' for char in component)
                or PureWindowsPath(component).is_reserved()):
            raise Refusal("Unsafe or reserved path component")


def reject_link(path):
    validate_path_text(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise Refusal("Links/reparse points are not supported")
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        raise Refusal("Only regular files and directories are supported")
    if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
        raise Refusal("Hard links are not supported")


def root_path(value):
    validate_path_text(value)
    root = Path(os.path.abspath(value))
    for part in [*reversed(root.parents), root]:
        reject_link(part)
    if root == Path(root.anchor) or not root.is_dir():
        raise Refusal("Target must be an existing, dedicated directory, not a drive root")
    return root


def child(root, name):
    validate_path_text(root)
    validate_path_text(name)
    p = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or p.is_absolute() or any(x in ("", ".", "..") for x in name.split("/")):
        raise Refusal("Unsafe relative path")
    result = root.joinpath(*p.parts)
    if not result.is_relative_to(root):
        raise Refusal("Path escaped target")
    for part in [result, *result.parents]:
        reject_link(part)
        if part == root:
            break
    return result


def inspect_tree(root):
    for folder, dirs, files in os.walk(root, followlinks=False):
        for name in dirs + files:
            reject_link(Path(folder) / name)


def templates(modules, preset="recommended"):
    if modules not in ([], ["recovery"]):
        raise Refusal("Unknown module selection")
    if preset not in ("recommended", "minimal"):
        raise Refusal("Unknown preset")
    names = CORE + (RECOMMENDED if preset == "recommended" else []) + (RECOVERY if modules else [])
    return {name: child(BASE / "templates", name).read_bytes() for name in names}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Refusal("Duplicate JSON fields refused")
        result[key] = value
    return result


def load_json(path, limit=MAX_PROFILE_BYTES):
    info = path.stat()
    if not stat.S_ISREG(info.st_mode):
        raise Refusal("JSON input must be a regular file")
    if info.st_size > limit:
        raise Refusal("JSON exceeds size limit")
    raw = path.read_bytes()
    if len(raw) > limit:
        raise Refusal("JSON exceeds size limit")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object)


def file_path(value):
    validate_path_text(value)
    path = Path(os.path.abspath(value))
    for part in [*reversed(path.parents), path]:
        reject_link(part)
    if not path.parent.is_dir():
        raise Refusal("File parent must already exist")
    return path


def read_profile(value):
    data = load_json(file_path(value))
    if not isinstance(data, dict) or set(data) != {"schema", "version", "files"} or data["schema"] != PROFILE_SCHEMA or type(data["version"]) is not int or data["version"] != 1:
        raise Refusal("Unsupported private profile schema")
    files = data["files"]
    if not isinstance(files, dict) or "private/overlay.md" not in files or not set(files).issubset(PRIVATE):
        raise Refusal("Profile permits only private overlay and optional profile")
    result = {}
    for name in PRIVATE:
        if name in files:
            value = files[name]
            if not isinstance(value, str) or "\x00" in value or len(value.encode("utf-8")) > MAX_TEXT_BYTES:
                raise Refusal("Invalid or oversized profile text")
            result[name] = value.encode("utf-8")
    return result


def read_state(root):
    data = load_json(child(root, STATE))
    if not isinstance(data, dict) or data.get("version") != VERSION:
        raise Refusal("Unsupported state/version; keep the original release to manage old installations; no automatic upgrade")
    if set(data) != {"version", "preset", "modules", "files", "private_files"}:
        raise Refusal("Invalid state fields")
    if data["private_files"] not in ([PRIVATE[0]], PRIVATE):
        raise Refusal("Invalid private file declaration")
    expected = templates(data["modules"], data["preset"])
    expected.pop(PRIVATE[0])
    allowed = set(expected) | set(DEMO)
    if not isinstance(data["files"], dict) or not set(expected).issubset(data["files"]) or not set(data["files"]).issubset(allowed):
        raise Refusal("State contains unexpected managed paths")
    expected.update(DEMO)
    for name, checksum in data["files"].items():
        child(root, name)
        if checksum != digest(expected[name]):
            raise Refusal("State hash does not match this release")
    return data


def changes(root, state):
    return {name: ("missing" if not child(root, name).exists() else "ok" if digest(child(root, name).read_bytes()) == sha else "modified") for name, sha in state["files"].items()}


def create_files(root, payload):
    made, directories = [], []
    try:
        for name, data in payload.items():
            target = child(root, name)
            pending = []
            parent = target.parent
            while parent != root and not parent.exists():
                pending.append(parent)
                parent = parent.parent
            for parent in reversed(pending):
                parent.mkdir()
                directories.append(parent)
            with target.open("xb") as stream:
                made.append(target)
                stream.write(data)
    except Exception:
        for target in reversed(made):
            target.unlink()
        for directory in reversed(directories):
            directory.rmdir()
        raise


def run(args):
    if getattr(args, "profile", None) and args.command != "init":
        raise Refusal("--profile is supported only for init")
    if getattr(args, "output", None) and args.command != "export-profile":
        raise Refusal("--output is supported only for export-profile")
    root = root_path(args.target)
    inspect_tree(root)
    if args.command == "init":
        if any(root.iterdir()):
            raise Refusal("Init requires an empty directory; nothing was overwritten")
        preset = getattr(args, "preset", "recommended")
        modules = ["recovery"] if args.recovery or preset == "recommended" else []
        payload = templates(modules, preset)
        profile = read_profile(args.profile) if getattr(args, "profile", None) else {}
        payload.update(profile)
        private_files = [name for name in PRIVATE if name in payload]
        state = {"version": VERSION, "preset": preset, "modules": modules,
                 "private_files": private_files,
                 "files": {k: digest(v) for k, v in payload.items() if k not in PRIVATE}}
        payload[STATE] = encoded(state)
        if args.apply:
            create_files(root, payload)
        return {"action": "initialized" if args.apply else "preview", "preset": preset,
                "files": list(payload), "private_source": "Explicitly supplied by caller; review personal facts before adoption; preferences never grant permissions" if profile else "Blank local preferences"}
    state = read_state(root)
    status = changes(root, state)
    private_status = {name: "present" if child(root, name).is_file() else "missing" for name in state["private_files"]}
    for name, value in private_status.items():
        if value == "present":
            with child(root, name).open("rb") as stream:
                stream.read(1)
    if args.command == "export-profile":
        if not getattr(args, "output", None):
            raise Refusal("export-profile requires --output pointing to a new JSON file")
        output = file_path(args.output)
        if output.is_relative_to(root) or output.exists():
            raise Refusal("Profile output must be a new file outside the installed target")
        files = {}
        for name in PRIVATE:
            source = child(root, name)
            if source.exists():
                if source.stat().st_size > MAX_TEXT_BYTES:
                    raise Refusal("Private text exceeds size limit")
                value = source.read_bytes().decode("utf-8")
                if "\x00" in value or len(value.encode("utf-8")) > MAX_TEXT_BYTES:
                    raise Refusal("Invalid private text")
                files[name] = value
        if PRIVATE[0] not in files or any(value == "missing" for value in private_status.values()):
            raise Refusal("Required private preference files are missing")
        payload = encoded({"schema": PROFILE_SCHEMA, "version": 1, "files": files})
        if len(payload) > MAX_PROFILE_BYTES:
            raise Refusal("Profile exceeds size limit")
        if args.apply:
            create_files(output.parent, {output.name: payload})
        return {"action": "profile-exported" if args.apply else "preview", "files": list(files),
                "bytes": len(payload), "scope": "Only the two named private text files; review their contents for secrets before transfer. No permissions are granted."}
    if args.command in ("doctor", "recover"):
        report = {"version": VERSION, "files": status, "healthy": all(x != "missing" for x in [*status.values(), *private_status.values()]), "template_drift": [name for name, value in status.items() if value == "modified"], "missing": [name for name, value in {**status, **private_status}.items() if value == "missing"], "permissions": "Not inspected; configure in your agent runtime"}
        report["private_files"] = private_status
        report["usable"] = report["healthy"]
        report["assessment"] = "File availability and state integrity only; edited content is not semantically validated"
        if args.command == "recover" and report["usable"]:
            report["resume"] = "Read task.md and, when installed, recovery/checkpoint.md. Confirm inputs and completion criteria before continuing."
        return report
    if args.command == "demo":
        if any(x == "missing" for x in [*status.values(), *private_status.values()]):
            raise Refusal("Doctor must be healthy before the synthetic demo")
        if any(child(root, name).exists() for name in DEMO):
            raise Refusal("Demo output already exists; refusing overwrite")
        values = json.loads(DEMO["example/input.json"])["items"]
        assert {"count": len(values), "total": sum(values)} == json.loads(DEMO["example/result.json"])
        if args.apply:
            # Output files are created exclusively. A failed state update leaves outputs intact.
            create_files(root, DEMO)
            state["files"].update({k: digest(v) for k, v in DEMO.items()})
            temp = child(root, ".starter-state.next")
            with temp.open("xb") as stream:
                stream.write(encoded(state))
            os.replace(temp, child(root, STATE))
        return {"action": "demo-complete" if args.apply else "preview", "count": 3, "total": 10}
    if args.command in ("uninstall", "rollback"):
        removable = [name for name, value in status.items() if value == "ok"]
        preserved = [name for name, value in status.items() if value == "modified"]
        private = child(root, "private")
        if private.exists() and ".gitignore" in removable:
            remaining_private = [p for p in private.rglob("*") if p.is_file() and p.relative_to(root).as_posix() not in removable]
            if remaining_private:
                removable.remove(".gitignore")
                preserved.append(".gitignore")
        if args.apply:
            for name in removable:
                child(root, name).unlink()
            child(root, STATE).unlink()
            directories = {child(root, name).parent for name in state["files"]}
            for directory in sorted(directories, key=lambda x: len(x.parts), reverse=True):
                if directory != root and directory.exists() and not any(directory.iterdir()):
                    directory.rmdir()
        return {"action": "removed" if args.apply else "preview", "remove": removable + [STATE], "preserve_modified": preserved, "unmanaged": "All unlisted files are preserved"}
    raise Refusal("Unknown command")


def main():
    parser = argparse.ArgumentParser(description="Local Harness Starter: previews by default")
    parser.add_argument("command", choices=["init", "doctor", "recover", "demo", "uninstall", "rollback", "export-profile"])
    parser.add_argument("target")
    parser.add_argument("--apply", action="store_true", help="Write changes; omitted means dry-run")
    parser.add_argument("--recovery", action="store_true", help="Include optional checkpoint template on init")
    parser.add_argument("--preset", choices=["recommended", "minimal"], default="recommended")
    parser.add_argument("--profile", help="Import an explicitly selected private profile JSON on init; does not grant permissions")
    parser.add_argument("--output", help="New export-profile JSON outside target")
    args = parser.parse_args()
    try:
        result = run(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("healthy") is False else 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as error:
        # Do not echo exception contents, which may include local paths or user data.
        print(json.dumps({"error": str(error) if isinstance(error, Refusal) else "Invalid state or filesystem operation refused", "changed": "No successful action reported; inspect target if interrupted"}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
