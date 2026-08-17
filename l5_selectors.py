# LEVEL5 ID 各画面で使うセレクタ定義（変更があればここだけ直せばOK）

SELECTORS = {
    "top_login_btn": "a[href*='auth.level5-id.com/login']",
    "agree_btn": "a#submit",  # 利用規約の「同意して新規登録」
    "email_input": "input#form_email, input[name='form[email]'], input.kp_enter[placeholder*='メール']",
    "mail_received_checkbox": "input#form_mail_received",
    "send_btn": "a#submit, button[type='submit']",

    # verify（パスワード設定）画面
    "password_1": "input#form_password, input[name='form[password]'], input[placeholder*='パスワードを入力']",
    "password_2": "input#form_password_confirmation, input[name='form[password_confirmation]'], input[placeholder*='確認']",
    "register_btn": "a#submit, button[type='submit']",

    # ログイン画面
    "login_email": "input#form_email",
    "login_pass": "input#form_password",
    "login_btn": "a#submit, button[type='submit']",

    # 成功判定（ログイン後にある可能性の高い要素など）
    "login_success_hint": "a[href*='logout'], nav a[href*='mypage']",
}
