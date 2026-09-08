// Firebase Configuration for Examora AI (yt-c-c)
const firebaseConfig = {
  apiKey: "AIzaSyCjblO4bQgDDaCJbviaVo8TT3NeA0nMe4g",
  authDomain: "yt-c-c.firebaseapp.com",
  databaseURL: "https://yt-c-c-default-rtdb.firebaseio.com",
  projectId: "yt-c-c",
  storageBucket: "yt-c-c.appspot.com",
  messagingSenderId: "49805545148",
  appId: "1:49805545148:web:b18c72cf283d5bb0046b9a"
};

if (!firebase.apps.length) {
  firebase.initializeApp(firebaseConfig);
}
const auth = firebase.auth();
const db = firebase.database();
