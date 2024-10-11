# with-argparse

`with-argparse` is a very simple and tiny package adding support to create
and apply `argparse.ArgumentParser` objects automatically using the type 
annotations from a given python method:

```python3
from pathlib import Path
from with_argparse import with_argparse

@with_argparse
def sample_method(
    text_input: str,  # required argument
    another_text_input: str = None,  # default argument
    output_dir: Path = None,
    flag: bool = False,
):
    pass

sample_method()
```

will generate the argparse output:

```text
usage: scratch_2.py [-h] --text_input TEXT_INPUT
                    [--another_text_input ANOTHER_TEXT_INPUT]
                    [--output_dir OUTPUT_DIR] [--flag]
```

### Boolean values

- A `True` boolean default field `flag` is converted to `--no_flag`

### Configurability

- `with_opt_argparse` allows to override some of the default settings used