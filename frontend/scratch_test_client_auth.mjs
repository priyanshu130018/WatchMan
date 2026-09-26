import { createClient } from "@supabase/supabase-js";
import axios from "axios";

const SUPABASE_URL = "https://zmeiqgttotuhzighkjxj.supabase.co";
const ANON_KEY = "sb_publishable_3cxc1snbfG0wPSOOzN36_g_t0EbaRDv";
const BACKEND_URL = "http://localhost:8000/api";

const supabase = createClient(SUPABASE_URL, ANON_KEY);

async function run() {
  const rand = Math.random().toString(36).substring(2, 8);
  const email = `test_${rand}@watchman.io`;
  const password = "Password123!@#";

  console.log(`=== 1. Testing client.auth.signUp for ${email} ===`);
  const { data: signUpData, error: signUpError } = await supabase.auth.signUp({
    email,
    password,
    options: {
      data: {
        full_name: `Test Node ${rand}`,
        username: `user_${rand}`,
      },
    },
  });

  if (signUpError) {
    console.error("SignUp error:", signUpError);
    return;
  }
  console.log("SignUp successful!");
  console.log("User id:", signUpData.user?.id);
  console.log("Session present on signup:", Boolean(signUpData.session));
  console.log("Access token present:", Boolean(signUpData.session?.access_token));

  console.log(`\n=== 2. Logging out ===`);
  await supabase.auth.signOut();

  console.log(`\n=== 3. Testing client.auth.signInWithPassword for ${email} ===`);
  const { data: loginData, error: loginError } = await supabase.auth.signInWithPassword({
    email,
    password,
  });

  if (loginError) {
    console.error("Login error:", loginError);
    return;
  }
  console.log("Login successful!");
  console.log("Login session token present:", Boolean(loginData.session?.access_token));

  const token = loginData.session?.access_token;
  console.log(`\n=== 4. Fetching /auth/me from backend with login token ===`);
  const meRes = await axios.get(`${BACKEND_URL}/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  console.log("/auth/me response:", meRes.data);

  console.log(`\n=== 5. Fetching /users/me from backend ===`);
  const userMeRes = await axios.get(`${BACKEND_URL}/users/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  console.log("/users/me response:", userMeRes.data);
}

run().catch(console.error);
