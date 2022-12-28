WIP

CLI utility to compute the diff between two directories.

The initially supported output format will be overlayfs tar or direct file
output. These output will be such that they can be used as the upper layer in an
overlayfs mount alongside the left operand of the diff to produce the same
contents present in the right operand as the merged mount.

This tool is intended to be used by systems directly managing container image
contents.
