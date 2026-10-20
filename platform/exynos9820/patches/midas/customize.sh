LOG_STEP_IN "- Adding S21 FE (r9sxxx) MIDAS"
DELETE_FROM_WORK_DIR "vendor" "etc/midas"
DELETE_FROM_WORK_DIR "vendor" "etc/VslMesDetector"
ADD_TO_WORK_DIR "r9sxxx" "vendor" "etc/midas"
ADD_TO_WORK_DIR "r9sxxx" "vendor" "etc/VslMesDetector"
LOG_STEP_OUT

LOG "- Fixing MIDAS model detection"
LOG "- Mapping MIDAS model selector to the actual source firmware"
python3 "$SRC_DIR/scripts/s10/midas_config.py" "$WORK_DIR/vendor/etc/midas/midas_config.json" "$WORK_DIR/system/system/build.prop"

LOG_STEP_IN "- Adding S21 FE (r9sxxx) Photo Remaster Service"
DELETE_FROM_WORK_DIR "system" "system/priv-app/PhotoRemasterService/oat"
ADD_TO_WORK_DIR "r9sxxx" "system" "system/priv-app/PhotoRemasterService/PhotoRemasterService.apk"
LOG_STEP_OUT

LOG_STEP_IN "- Adding S21 FE (r9sxxx) MIDAS libraries"
ADD_TO_WORK_DIR "r9sxxx" "system" "system/lib64/libmidas_core.camera.samsung.so"
ADD_TO_WORK_DIR "r9sxxx" "system" "system/lib64/libmidas_DNNInterface.camera.samsung.so"
LOG_STEP_OUT
