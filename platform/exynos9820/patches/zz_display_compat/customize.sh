SKIPUNZIP=1
# The stock 3.1.0 S10 libraries do not match these older Exynos patterns.
# Preserve the compatibility rule for matching drivers; never force it.
python3 "$SRC_DIR/scripts/s10/optional_binary_patch.py" display-ddiscaler-64 \
  "$WORK_DIR/vendor/lib64/libexynosdisplay.so"
python3 "$SRC_DIR/scripts/s10/optional_binary_patch.py" display-ddiscaler-32 \
  "$WORK_DIR/vendor/lib/libexynosdisplay.so"
