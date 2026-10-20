# SPDX-License-Identifier: GPL-3.0-or-later
LOG_STEP_IN "- Installing pinned S10 kernel artifacts"
python3 "$SRC_DIR/scripts/s10/kernel_artifacts.py" "$SRC_DIR/kernel-artifacts/$TARGET_CODENAME" "$WORK_DIR/kernel" "$TARGET_CODENAME"
LOG_STEP_OUT
