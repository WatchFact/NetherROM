# Original 3.1.0 diffs are retained under reference-smali for provenance.
# Android 16/One UI 8.5 may place these classes in different dex files.
DECODE_APK "system" "system/priv-app/SecSettings/SecSettings.apk"
DECODE_APK "system_ext" "priv-app/SystemUI/SystemUI.apk"
python3 "$SRC_DIR/scripts/s10/extradim.py" \
  "$APKTOOL_DIR/system/priv-app/SecSettings/SecSettings.apk" \
  "$APKTOOL_DIR/system_ext/priv-app/SystemUI/SystemUI.apk"
