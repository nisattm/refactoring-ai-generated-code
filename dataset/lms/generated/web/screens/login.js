// LIB-UI-GEN-04: login screen.

import { api } from "../api.js";
import { field, form, replace } from "../ui.js";

export const loginScreen = {
  id: "login",
  title: "Log in",
  roles: ["all"],
  render(ctx, { onLoggedIn }) {
    const email = field({ name: "email", label: "Email", type: "email", autocomplete: "username" });
    const password = field({ name: "password", label: "Password", type: "password", autocomplete: "current-password" });
    const node = form({
      fields: [email, password],
      submit: "Log in",
      label: "Log in",
      async onSubmit(values) {
        ctx.clearMessages();
        try {
          const result = await api("POST", "/auth/login", {
            body: { email: values.email.trim(), password: values.password },
            auth: false,
          });
          onLoggedIn(result.access_token, result.user);
        } catch (error) {
          ctx.fail(error);
        }
      },
    });
    replace(ctx.body, node);
  },
};
