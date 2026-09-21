package com.wellphone.probe.ime;

import android.inputmethodservice.InputMethodService;
import android.os.Process;
import android.os.SystemClock;
import android.util.Log;
import android.view.View;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import org.json.JSONException;
import org.json.JSONObject;

/** Fixed synthetic input only. This is not a real pinyin keyboard. */
public final class ProbeIme extends InputMethodService {
    private static final String TAG = "WellphoneProbeIME";
    private final long instance = SystemClock.elapsedRealtimeNanos();
    private int seq;
    private int starts;
    private int finishes;
    private int viewStarts;
    private int viewFinishes;
    private String targetPackage = "";
    private int fieldId;
    private TextView status;

    @Override public View onCreateInputView() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setBackgroundColor(0xffdddddd);
        status = new TextView(this);
        status.setText("SYNTHETIC PROBE IME — not a pinyin keyboard");
        status.setTextSize(12);
        layout.addView(status);
        row(layout, "COMPOSE ni", "COMPOSE nihao", 0, 1);
        row(layout, "COMMIT 你好", "COMMIT A", 2, 3);
        row(layout, "FINISH COMPOSING", "IME SNAPSHOT", 4, 5);
        emit("input_view_created", null, null);
        return layout;
    }

    private void row(LinearLayout layout, String left, String right, int leftOp, int rightOp) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        button(row, left, leftOp);
        button(row, right, rightOp);
        layout.addView(row);
    }

    private void button(LinearLayout row, String label, int operation) {
        Button b = new Button(this);
        b.setText(label);
        b.setContentDescription(label);
        b.setFocusable(false);
        b.setOnClickListener(view -> perform(operation));
        int height = Math.round(52 * getResources().getDisplayMetrics().density);
        row.addView(b, new LinearLayout.LayoutParams(0, height, 1));
    }

    private void perform(int operation) {
        if (operation == 5) { emit("snapshot", null, null); return; }
        InputConnection connection = getCurrentInputConnection();
        // The OS can select this IME for any app. Deliberately refuse input outside fixtures.
        if (!targetPackage.equals("com.wellphone.probe.main")
                && !targetPackage.equals("com.wellphone.probe.agent")) {
            emit("refused_non_fixture_target", null, false);
            return;
        }
        if (connection == null) { emit("no_input_connection", null, false); return; }
        String event;
        String text = null;
        boolean result;
        switch (operation) {
            case 0: event = "set_composing_text"; text = "ni";
                result = connection.setComposingText(text, 1); break;
            case 1: event = "set_composing_text"; text = "nihao";
                result = connection.setComposingText(text, 1); break;
            case 2: event = "commit_text"; text = "你好";
                result = connection.commitText(text, 1); break;
            case 3: event = "commit_text"; text = "A";
                result = connection.commitText(text, 1); break;
            case 4: event = "finish_composing_text";
                result = connection.finishComposingText(); break;
            default: throw new IllegalArgumentException("Unknown fixed probe operation");
        }
        emit(event, text, result);
    }

    @Override public void onStartInput(EditorInfo info, boolean restarting) {
        super.onStartInput(info, restarting);
        starts++;
        targetPackage = info == null || info.packageName == null ? "" : info.packageName;
        fieldId = info == null ? 0 : info.fieldId;
        emit(restarting ? "start_input_restart" : "start_input", null, null);
    }

    @Override public void onFinishInput() {
        finishes++;
        emit("finish_input", null, null);
        super.onFinishInput();
        targetPackage = "";
        fieldId = 0;
    }

    @Override public void onStartInputView(EditorInfo info, boolean restarting) {
        super.onStartInputView(info, restarting);
        viewStarts++;
        emit(restarting ? "start_input_view_restart" : "start_input_view", null, null);
    }

    @Override public void onFinishInputView(boolean finishingInput) {
        viewFinishes++;
        emit(finishingInput ? "finish_input_view_and_input" : "finish_input_view", null, null);
        super.onFinishInputView(finishingInput);
    }

    @Override public boolean onEvaluateFullscreenMode() { return false; }

    private void emit(String event, String syntheticText, Boolean result) {
        try {
            JSONObject value = new JSONObject();
            value.put("event", event);
            value.put("seq", ++seq);
            value.put("elapsed_ns", SystemClock.elapsedRealtimeNanos());
            value.put("pid", Process.myPid());
            value.put("instance", instance);
            value.put("target_package", targetPackage);
            value.put("field_id", fieldId);
            value.put("input_starts", starts);
            value.put("input_finishes", finishes);
            value.put("view_starts", viewStarts);
            value.put("view_finishes", viewFinishes);
            if (syntheticText != null) value.put("synthetic_text", syntheticText);
            if (result != null) value.put("result", result);
            Log.i(TAG, value.toString());
            if (status != null) status.setText("SYNTHETIC PROBE IME\n" + targetPackage
                    + " start=" + starts + " finish=" + finishes + " " + event);
        } catch (JSONException error) {
            throw new IllegalStateException("Probe IME event serialization failed", error);
        }
    }
}
