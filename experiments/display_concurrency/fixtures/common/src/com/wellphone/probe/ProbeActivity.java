package com.wellphone.probe;

import android.app.Activity;
import android.content.Context;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Process;
import android.os.SystemClock;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.WindowInsets;
import android.view.inputmethod.BaseInputConnection;
import android.view.inputmethod.EditorInfo;
import android.view.inputmethod.InputConnection;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import org.json.JSONException;
import org.json.JSONObject;

/** Disposable synthetic editor. Native accessibility behavior is not overridden. */
public final class ProbeActivity extends Activity {
    private static final String TAG = "WellphoneProbe";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final long instance = SystemClock.elapsedRealtimeNanos();
    private ProbeEditor editor;
    private TextView stateView;
    private String lastState = "";
    private int eventSeq;
    private int counter;
    private int sampleSeq;
    private int focusGained;
    private int focusLost;
    private int inputConnections;
    private boolean resumed;
    private boolean destroyed;
    private final Runnable sampler = new Runnable() {
        @Override public void run() {
            emit("state_changed", false);
            if (!destroyed) handler.postDelayed(this, 100);
        }
    };

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        LinearLayout content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(12);
        content.setPadding(pad, pad, pad, pad);
        TextView title = new TextView(this);
        title.setText(getPackageName() + "\nSYNTHETIC INPUT ONLY");
        title.setTextSize(18);
        content.addView(title);

        editor = new ProbeEditor(this);
        editor.setId(id("probe_editor"));
        editor.setHint("Synthetic probe editor");
        editor.setContentDescription("probe_editor");
        editor.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        editor.setImeOptions(EditorInfo.IME_FLAG_NO_EXTRACT_UI);
        editor.setMinLines(2);
        editor.setGravity(Gravity.TOP);
        content.addView(editor, new LinearLayout.LayoutParams(-1, dp(112)));
        editor.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {}
            @Override public void afterTextChanged(Editable value) {
                emit("text_changed", true);
                handler.post(() -> emit("text_settled", true));
            }
        });
        editor.setOnFocusChangeListener((view, focused) -> emit("editor_focus_changed", true));

        button(content, "probe_show_ime", "FOCUS EDITOR / SHOW IME", () -> {
            editor.requestFocus();
            ((InputMethodManager) getSystemService(INPUT_METHOD_SERVICE))
                    .showSoftInput(editor, InputMethodManager.SHOW_IMPLICIT);
            emit("show_ime_clicked", true);
        });
        button(content, "probe_counter", "COUNT 0", () -> {
            counter++;
            ((Button) findViewById(id("probe_counter"))).setText("COUNT " + counter);
            emit("counter_clicked", true);
        });
        button(content, "probe_readback", "READBACK", () -> emit("readback", true));
        if (getPackageName().endsWith(".agent")) {
            button(content, "probe_set_sample", "SET SAMPLE LOCALLY", () -> {
                editor.setText("agent-中文-😀-" + (++sampleSeq));
                editor.setSelection(editor.length());
                emit("local_set_sample", true);
            });
        }
        stateView = new TextView(this);
        stateView.setId(id("probe_state"));
        stateView.setTextSize(12);
        stateView.setTextIsSelectable(false);
        content.addView(stateView);
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.addView(content);
        setContentView(scroll);
        emit("created", true);
        handler.post(sampler);
    }

    private int id(String name) { return getResources().getIdentifier(name, "id", getPackageName()); }
    private int dp(int value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    private void button(LinearLayout parent, String idName, String label, Runnable action) {
        Button b = new Button(this);
        b.setId(id(idName));
        b.setText(label);
        // Touch buttons do not take editor focus; window-focus changes remain observable.
        b.setFocusable(false);
        b.setOnClickListener(view -> action.run());
        parent.addView(b, new LinearLayout.LayoutParams(-1, dp(48)));
    }

    @Override public void onResume() {
        super.onResume();
        resumed = true;
        emit("resumed", true);
    }

    @Override public void onPause() {
        resumed = false;
        emit("paused", true);
        super.onPause();
    }

    @Override public void onWindowFocusChanged(boolean focused) {
        super.onWindowFocusChanged(focused);
        if (focused) focusGained++; else focusLost++;
        emit("window_focus_changed", true);
    }

    @Override public void onDestroy() {
        emit("destroyed", true);
        destroyed = true;
        handler.removeCallbacksAndMessages(null);
        super.onDestroy();
    }

    private void emit(String event, boolean force) {
        if (editor == null) return;
        try {
            Editable text = editor.getText();
            WindowInsets insets = editor.getRootWindowInsets();
            JSONObject value = new JSONObject();
            value.put("package", getPackageName());
            value.put("pid", Process.myPid());
            value.put("instance", instance);
            value.put("display_id", editor.getDisplay() == null ? -1 : editor.getDisplay().getDisplayId());
            value.put("text", text.toString());
            value.put("selection_start", editor.getSelectionStart());
            value.put("selection_end", editor.getSelectionEnd());
            value.put("composing_start", BaseInputConnection.getComposingSpanStart(text));
            value.put("composing_end", BaseInputConnection.getComposingSpanEnd(text));
            value.put("window_focus", hasWindowFocus());
            value.put("editor_focus", editor.hasFocus());
            value.put("resumed", resumed);
            value.put("window_focus_gained", focusGained);
            value.put("window_focus_lost", focusLost);
            value.put("input_connections", inputConnections);
            value.put("counter", counter);
            if (Build.VERSION.SDK_INT >= 30 && insets != null) {
                value.put("ime_visible", insets.isVisible(WindowInsets.Type.ime()));
                value.put("ime_bottom", insets.getInsets(WindowInsets.Type.ime()).bottom);
            }
            String state = value.toString();
            if (!force && state.equals(lastState)) return;
            lastState = state;
            value.put("event", event);
            value.put("seq", ++eventSeq);
            value.put("elapsed_ns", SystemClock.elapsedRealtimeNanos());
            String line = value.toString();
            Log.i(TAG, line);
            if (stateView != null) stateView.setText(line);
        } catch (JSONException error) {
            throw new IllegalStateException("Probe state serialization failed", error);
        }
    }

    private final class ProbeEditor extends EditText {
        ProbeEditor(Context context) { super(context); }

        @Override protected void onSelectionChanged(int start, int end) {
            super.onSelectionChanged(start, end);
            emit("selection_changed", true);
        }

        @Override public InputConnection onCreateInputConnection(EditorInfo outAttrs) {
            InputConnection connection = super.onCreateInputConnection(outAttrs);
            inputConnections++;
            emit("input_connection_created", true);
            return connection;
        }
    }
}
