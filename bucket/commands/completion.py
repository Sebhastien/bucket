from __future__ import annotations

import typer

from bucket.main import emit


def register(app: typer.Typer) -> None:
    completion_app = typer.Typer(no_args_is_help=True)

    @completion_app.command("install")
    def install(
        ctx: typer.Context,
        shell: str | None = typer.Option(
            None,
            "--shell",
            help="Shell to install completion for (bash, zsh, fish). Detected automatically if omitted.",
        ),
    ) -> None:
        """Install shell tab completion for bucket."""
        from typer.completion import install as typer_install

        detected_shell, path = typer_install(shell=shell, prog_name="bucket")
        msg = f"{detected_shell} completion installed in {path}\n"
        msg += "Completion will take effect once you restart the terminal."
        emit(ctx, {"shell": detected_shell, "path": str(path)}, lambda console: console.print(msg))

    @completion_app.command("show")
    def show(
        ctx: typer.Context,
        shell: str | None = typer.Option(
            None,
            "--shell",
            help="Shell to show completion for (bash, zsh, fish). Detected automatically if omitted.",
        ),
    ) -> None:
        """Print the shell completion script to stdout."""
        from typer.completion import _get_shell_name, get_completion_script

        prog_name = "bucket"
        complete_var = f"_{prog_name.upper()}_COMPLETE"
        target_shell = shell or _get_shell_name() or ""
        script = get_completion_script(
            prog_name=prog_name, complete_var=complete_var, shell=target_shell
        )
        emit(ctx, {"shell": target_shell, "script": script}, lambda console: console.print(script))

    app.add_typer(completion_app, name="completion")
