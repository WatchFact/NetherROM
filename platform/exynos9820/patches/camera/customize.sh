# Reviewed NetherROM Exynos9820 camera patch (derived from ArtisanROM v3.1.0)
# This module runs INSIDE make_rom.sh against WORK_DIR; source-controlled, not generated.
LOG_STEP_IN "- Replacing camera blobs"
BLOBS_LIST="
system/lib64/libenn_wrapper_system.so
system/lib64/libpic_best.arcsoft.so
system/lib64/libarcsoft_dualcam_portraitlighting.so
system/lib64/libdualcam_refocus_gallery_54.so
system/lib64/libdualcam_refocus_gallery_48.so
system/lib64/libhybrid_high_dynamic_range.arcsoft.so
system/lib64/libae_bracket_hdr.arcsoft.so
system/lib64/libface_recognition.arcsoft.so
system/lib64/libDualCamBokehCapture.camera.samsung.so
"
for blob in $BLOBS_LIST
do
    DELETE_FROM_WORK_DIR "system" "$blob"
done


BLOBS_LIST="
system/lib64/libPortraitDistortionCorrectionCali.arcsoft.so
system/lib64/libMultiFrameProcessing10.camera.samsung.so
system/lib64/libMultiFrameProcessing20.camera.samsung.so
system/lib64/libMultiFrameProcessing20Day.camera.samsung.so
system/lib64/libMultiFrameProcessing30.camera.samsung.so
system/lib64/libMultiFrameProcessing30Tuning.camera.samsung.so
system/lib64/vendor.samsung_slsi.hardware.iva@1.0.so
system/lib64/vendor.samsung_slsi.hardware.MultiFrameProcessing20@1.0.so
"
for blob in $BLOBS_LIST
do
    ADD_TO_WORK_DIR "$TARGET_FIRMWARE" "system" "$blob" 0 0 644 "u:object_r:system_lib_file:s0"
done


LOG_STEP_OUT

LOG_STEP_IN
LOG "- Patching Video SVC Check"
# Early jump after the log and abort functions when configureSVC fails
# b LAB_001dd448 -> b LAB_001ddc24
python3 "$SRC_DIR/scripts/s10/optional_binary_patch.py" stagefright-video-svc "$WORK_DIR/system/system/lib64/libstagefright.so"

LOG "- Patching HDR10+ Check"
# Skip HDR10+ Recording ASSERT
# cbz this,LAB_001dde38 -> nop
python3 "$SRC_DIR/scripts/s10/optional_binary_patch.py" stagefright-hdr10 "$WORK_DIR/system/system/lib64/libstagefright.so"
LOG_STEP_OUT

BLOBS_LIST="
system/lib64/libeden_wrapper_system.so
system/lib64/libsnap_aidl.snap.samsung.so
"
for blob in $BLOBS_LIST
do
    ADD_TO_WORK_DIR "p3sxxx" "system" "$blob" 0 0 644 "u:object_r:system_lib_file:s0"
done
LOG_STEP_OUT

LOG_STEP_IN "- Adding S21 FE (r9sxxx) SWISP models"
DELETE_FROM_WORK_DIR "vendor" "saiv/swisp_1.0"
ADD_TO_WORK_DIR "p3sxxx" "vendor" "saiv/swisp_1.0"

BLOBS_LIST="
system/lib64/libSwIsp_core.camera.samsung.so
system/lib64/libSwIsp_wrapper_v1.camera.samsung.so
"
for blob in $BLOBS_LIST
do
    ADD_TO_WORK_DIR "p3sxxx" "system" "$blob" 0 0 644 "u:object_r:system_lib_file:s0"
done
LOG_STEP_OUT

LOG_STEP_IN "- Adding A26 (a26xxx) Polarr SDK blobs"
ADD_TO_WORK_DIR "a73xqxx" "system" "system/etc/public.libraries-polarr.txt" 0 0 644 "u:object_r:system_file:s0"
ADD_TO_WORK_DIR "a73xqxx" "system" "system/lib64/libBestComposition.polarr.so" 0 0 644 "u:object_r:system_lib_file:s0"
ADD_TO_WORK_DIR "a73xqxx" "system" "system/lib64/libFeature.polarr.so" 0 0 644 "u:object_r:system_lib_file:s0"
ADD_TO_WORK_DIR "a73xqxx" "system" "system/lib64/libTracking.polarr.so" 0 0 644 "u:object_r:system_lib_file:s0"
LOG_STEP_OUT

LOG_STEP_IN "- Cleaning SamsungCamera OAT"
DELETE_FROM_WORK_DIR "system" "system/priv-app/SamsungCamera/oat"
DELETE_FROM_WORK_DIR "system" "system/priv-app/SamsungCamera/SamsungCamera.apk.prof"
DELETE_FROM_WORK_DIR "system" "system/app/FilterProvider/oat"
LOG_STEP_OUT

LOG_STEP_IN "- Fixing AI Photo Editor"
cp -a --preserve=all \
    "$WORK_DIR/system/system/cameradata/portrait_data/single_bokeh_feature.json" \
    "$WORK_DIR/system/system/cameradata/portrait_data/nexus_bokeh_feature.json"
SET_METADATA "system" "system/cameradata/portrait_data/nexus_bokeh_feature.json" 0 0 644 "u:object_r:system_file:s0"
sed -i "s/MODEL_TYPE_INSTANCE_CAPTURE/MODEL_TYPE_OBJ_INSTANCE_CAPTURE/g" \
    "$WORK_DIR/system/system/cameradata/portrait_data/single_bokeh_feature.json"
python3 "$SRC_DIR/scripts/s10/camera_path_patch.py" \
    "$WORK_DIR/system/system/lib64/libPortraitSolution.camera.samsung.so"
python3 "$SRC_DIR/scripts/s10/camera_portrait.py" record "$WORK_DIR" "$TARGET_CODENAME" \
    "$FW_DIR/$(cut -d / -f 1 <<< "$SOURCE_FIRMWARE")_$(cut -d / -f 2 <<< "$SOURCE_FIRMWARE")"
LOG_STEP_OUT

LOG_STEP_IN "- Adding S21 FE (r9sxxx) SingleTake models"
DELETE_FROM_WORK_DIR "vendor" "etc/singletake"
ADD_TO_WORK_DIR "p3sxxx" "vendor" "etc/singletake"

BLOBS_LIST="
system/priv-app/SingleTakeService/SingleTakeService.apk
system/cameradata/singletake/service-feature.xml
"
for blob in $BLOBS_LIST
do
    ADD_TO_WORK_DIR "p3sxxx" "system" "$blob" 0 0 644 "u:object_r:system_file:s0"
done


LOG "- Decompiling SamsungCamera" # To fool build system into recompiling + signing it at the end
DECODE_APK "system" "system/priv-app/SamsungCamera/SamsungCamera.apk"

if [[ "$TARGET_CODENAME" == "beyond2lte" ]]; then
   LOG "- Adding stock cutout assets"
   cp -a "$MODPATH/assets/lottie_camera_punchcut_timer_b2.json" "$APKTOOL_DIR/system/priv-app/SamsungCamera/SamsungCamera.apk/res/raw/lottie_camera_punchcut_timer_b0.json"
   cp -a "$MODPATH/assets/face_unlocking_cutout_ic_b2.json" "$APKTOOL_DIR/system/priv-app/SamsungCamera/SamsungCamera.apk/res/raw/face_unlocking_cutout_ic_b0.json"
fi

if [[ "$TARGET_CODENAME" == "beyondx" ]]; then
   LOG "- Adding stock cutout assets"
   cp -a "$MODPATH/assets/lottie_camera_punchcut_timer_bx.json" "$APKTOOL_DIR/system/priv-app/SamsungCamera/SamsungCamera.apk/res/raw/lottie_camera_punchcut_timer_b0.json"
   cp -a "$MODPATH/assets/face_unlocking_cutout_ic_bx.json" "$APKTOOL_DIR/system/priv-app/SamsungCamera/SamsungCamera.apk/res/raw/face_unlocking_cutout_ic_b0.json"
fi

LOG_STEP_OUT

# S10 camera compatibility: vetted Polarr public library list.
POLARR_PUBLIC_LIBS="$WORK_DIR/system/system/etc/public.libraries-polarr.txt"
test -f "$POLARR_PUBLIC_LIBS" || {
    ABORT "Missing Exynos9820 Polarr public-libraries list"
    return 1
}
sed -i -e '/^libPolarrSnap\.polarr\.so$/d' \
       -e '/^libYuv\.polarr\.so$/d' "$POLARR_PUBLIC_LIBS"
unset POLARR_PUBLIC_LIBS
