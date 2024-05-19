# uniondiff - Directory difference calculator

*uniondiff* is a simple tool for calculating the directory difference between two
directories or archives. *uniondiff* performs the calculation below:

```
upper = merged - lower
```

This tool acts as the inverse [union mount](https://en.wikipedia.org/wiki/Union_mount)
file systems. Whereas typically you combine a *lower* and *upper* directory to
produce a *merged* directory, *uniondiff* takes as input the *merged* directory
and subtracts out the *lower* directory to produce the *upper* directory. In
particular, the resulting output can be mounted as the *upper* directory
along with the *lower* to produce the original *merged* directory.

*uniondiff* is intended for use with low level file system tools (e.g. container
systems) or for simply storing diffs of directories. Note that this tool *does
not* store compact diffs of individual files; a file will appear in full in the
diff iff its content or metadata has changed between the *merged* and *lower*
operands.

## Installation

*uniondiff* can be installed through *pip*. This installs both the `uniondiff`
CLI utility and the *uniondiff* Python library.

```sh
pip install uniondiff
```

*uniondiff* is supported and tested on Python 3.8-3.12

## Examples

Compute the directory difference between the directory "data-day10" and
"data-day9". By default the output will be written as a tar file.

```sh
uniondiff data-day10 data-day9 > diff.tar
```

*uniondiff* can also write directly to the file system. Note that it will ignore
ownership changes unless you also pass the `--preserve-owners` flag.

```sh
uniondiff data-day10 data-day9 --output-type file -o diff
```

You can also use tar archives as the input paths.

```sh
uniondiff data-day10.tar data-day9.tgz > diff.tar
```

## Contributing

If you want to contribute to *uniondiff*, you can do so by creating a pull request.
lease make sure to include a detailed description of the changes you're proposing.
