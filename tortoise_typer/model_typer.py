import asyncio
from datetime import datetime
from inspect import Parameter, Signature
from typing import Any, Iterable

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from tortoise import exceptions, fields, models
from typer import Argument, Option, Typer


def _make_panel_printer(title: str, border_style: str) -> callable:
    """Creates a printer function that displays messages in a styled panel.

    Args:
        title (str): The title of the panel.
        border_style (str): The style of the panel border.

    Returns:
        callable: A function that takes a message string and prints it in
            a styled panel.

    """
    def printer(message: str) -> None:
        console = Console()
        text = Text(message, style="bold")
        panel = Panel(
            text,
            border_style=border_style,
            title=title,
            title_align="left",
        )

        console.print(panel)

    return printer


def listing(title: str, instances: Iterable[Any]) -> None:
    """Prints a list of instances in a styled panel.

    Args:
        title (str): The title of the panel.
        instances (Iterable[Any]): A collection of instances to list.

    """
    console = Console()
    table = Table(show_header=True)
    table.add_column("#", style="dim", width=4)
    table.add_column(title, style="bold")

    for i, instance in enumerate(instances, start=1):
        table.add_row(str(i), str(instance))

    console.print(table)


error = _make_panel_printer("Error", "red")
warning = _make_panel_printer("Warning", "yellow")
info = _make_panel_printer("Info", "white")


class ModelTyper(Typer):
    """A Typer app for managing Tortoise ORM models.

    This class provides a command-line interface for creating, editing,
    listing, showing, and deleting Tortoise ORM model instances.

    Args:
        model (tortoise.Model): The Tortoise ORM model to manage.

    """

    def __init__(self, model: models.Model, *args: tuple, **kwargs: dict) -> None:
        super().__init__(*args, **kwargs)
        self._add_model_methods(model)

    def _get_field_type(self, field: fields.Field) -> type:
        if isinstance(field, fields.IntField):
            return int
        elif isinstance(field, fields.BooleanField):
            return bool
        elif isinstance(field, fields.DatetimeField):
            return datetime
        elif isinstance(field, fields.DateField):
            # Not currently supported by typer.
            return datetime.date
        else:
            return str

    def _inject_model_signature(
        self,
        model: models.Model,
        func: callable,
        force_optional: bool = False,
        add_id_argument: bool = False
    ) -> callable:
        parameters = []
        if add_id_argument:
            parameters.append(
                Parameter(
                    name="id",
                    kind=Parameter.POSITIONAL_ONLY,
                    default=Argument(..., help="ID of the instance"),
                    annotation=int
                )
            )

        for name, field in model._meta.fields_map.items():
            param_type = self._get_field_type(field)
            if (
                field.pk
                or hasattr(field, 'auto_now') and field.auto_now
                or hasattr(field, 'auto_now_add') and field.auto_now_add
            ):
                continue

            is_required = (
                not field.null
                and field.default is None
                and not force_optional
            )

            parameters.append(
                Parameter(
                    name=name,
                    kind=Parameter.KEYWORD_ONLY,
                    default=Option(... if is_required else None),
                    annotation=param_type,
                )
            )

        func.__signature__ = Signature(parameters)

        return func

    def _add_model_methods(self, model: models.Model) -> None:
        """Add a model to the typer app.

        Args:
            model (models.Model): The model to to the typer app.

        Raises:
            TypeError: If the model is not a subclass of tortoise.models.Model.

        """
        name = model.__name__.upper()
        id_argument = Argument(..., help="ID of the instance")
        if not issubclass(model, models.Model):
            raise TypeError(
                f"The model {model} is not a subclass of tortoise.models.Model"
            )

        def _show(instance: model) -> None:
            info(
                "\n".join(f"* {field}: {getattr(instance, field)}"
                for field in model._meta.fields_map)
            )

        def create(**kwargs: dict) -> None:
            async def acreate() -> model:
                instance = await model.create(**kwargs)
                await instance.save()
                return instance

            instance = asyncio.run(acreate())
            _show(instance)

        def edit(**kwargs: dict) -> None:
            args = kwargs.copy()

            async def aedit() -> model:
                id = args.pop("id")
                instance = await model.get(id=id)
                for key, value in args.items():
                    if value is not None:
                        setattr(instance, key, value)
                await instance.save()
                return instance

            instance = asyncio.run(aedit())
            _show(instance)

        def list() -> None:
            async def alist() -> list[model]:
                return await model.all()

            instances = asyncio.run(alist())
            if not instances:
                warning(f"No {name} instances found.")
                return

            listing(name, instances)

        def show(id: int = id_argument) -> None:
            async def ashow() -> model:
                return await model.get(id=id)

            try:
                instance = asyncio.run(ashow())
            except exceptions.DoesNotExist:
                error(f"{name} with ID {id} not found.")
                return

            _show(instance)

        def delete(id: int = id_argument) -> None:
            async def adelete() -> None:
                instance = await model.get(id=id)
                await instance.delete()

            try:
                asyncio.run(adelete())
                info(f"{name} with ID {id} deleted successfully.")
            except exceptions.DoesNotExist:
                error(f"{name} with ID {id} not found.")

        self.command(name="list", help=f"List all {name} instances.")(list)
        self.command(
            name="delete", help=f"Delete a specific {name} instance."
        )(delete)
        self.command(
            name="show", help=f"Show a specific {name} instance."
        )(show)
        self.command(name="create", help=f"Create a new {name} instance.")(
            self._inject_model_signature(model, create)
        )
        self.command(name="edit", help=f"Edit an existing {name} instance.")(
            self._inject_model_signature(
                model,
                edit,
                force_optional=True,
                add_id_argument=True
            )
        )
