# Tortoise Typer

Module to turn any Tortoise ORM model into a Typer CLI application.

# Example Usage

Simply add a `ModelTyper` instance to your Typer application, passing the model class you want to manage. We
let you choose how to initialise and close the Tortoise ORM connections, so you can integrate it into your existing
application without any issues.

```python
import asyncio

from tortoise import Tortoise
from typer import Typer
from tortoise_typer import ModelTyper

from myapp.models import MyModel 
from myapp.config import CONFIG

app = Typer()
app.add_typer(
    ModelTyper(MyModel),
    name="mymodel",  # default subcommand name
    help="Manage MyModel instances",
)

if __name__ == "__main__":
    asyncio.run(Tortoise.init(config=CONFIG))
    
    try:
        app()
    finally:
        asyncio.run(Tortoise.close_connections())
```
