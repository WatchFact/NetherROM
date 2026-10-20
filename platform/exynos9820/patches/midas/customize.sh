# Reviewed NetherROM Exynos9820 MIDAS patch (derived from ArtisanROM v3.1.0)
# Imports actual p3sxxx models and libraries into WORK_DIR.
LOG_STEP_IN "- Adding S21 FE (r9sxxx) MIDAS"
DELETE_FROM_WORK_DIR "vendor" "etc/midas"
DELETE_FROM_WORK_DIR "vendor" "etc/VslMesDetector"
ADD_TO_WORK_DIR "p3sxxx" "vendor" "etc/midas"
ADD_TO_WORK_DIR "p3sxxx" "vendor" "etc/VslMesDetector"
LOG_STEP_OUT

LOG "- Validating MIDAS model detection against real donor identity"
python3 "$SRC_DIR/scripts/s10/validate_midas.py" \
    "$WORK_DIR/vendor/etc/midas/midas_config.json" \
    "$WORK_DIR/system/system/build.prop"

LOG_STEP_IN "- Adding S21 FE (r9sxxx) Photo Remaster Service"
DELETE_FROM_WORK_DIR "system" "system/priv-app/PhotoRemasterService/oat"
ADD_TO_WORK_DIR "p3sxxx" "system" "system/priv-app/PhotoRemasterService/PhotoRemasterService.apk"
LOG_STEP_OUT

LOG_STEP_IN "- Adding S21 FE (r9sxxx) MIDAS libraries"
ADD_TO_WORK_DIR "p3sxxx" "system" "system/lib64/libmidas_core.camera.samsung.so"
ADD_TO_WORK_DIR "p3sxxx" "system" "system/lib64/libmidas_DNNInterface.camera.samsung.so"
LOG_STEP_OUT
