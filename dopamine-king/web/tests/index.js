"use strict";
// Entry point for `node --test web/tests/`.
// Node 21 and later treat a directory argument like a module path instead of searching it, so this file
// is what that command resolves to. It loads every *.test.js file in this folder so they all run and report
// together; each file can still be run on its own, for example `node --test web/tests/game.test.js`.
const fs = require("node:fs");
const path = require("node:path");

fs.readdirSync(__dirname)
  .filter((name) => name.endsWith(".test.js"))
  .sort()
  .forEach((name) => require(path.join(__dirname, name)));
