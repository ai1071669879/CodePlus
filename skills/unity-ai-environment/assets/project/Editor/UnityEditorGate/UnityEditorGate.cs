// UnityEditorGate — file-based control channel for a running Unity Editor.
//
// Copy this folder into a project (any folder named Editor works, e.g. <project>/Editor/).
// It starts automatically ([InitializeOnLoad]) and polls a request file, so an external
// agent can ask the already-open Editor to refresh assets or run an authorized static
// Editor method without driving the UI. It never starts Unity and never runs shell.
//
// Protocol (schema_version 1), root = <project>/Temp/UnityEditorGate/<pid>/
//   request.json : {"schema_version":1,"id":"<ascii>","suite":"refresh|wait-compile|invoke",
//                   "type":"<Type>","method":"<static method>","args":["..."],"note":"..."}
//   status.json  : latest receipt {status: ready|busy|started|observed|failed, ok, id, suite,
//                   pid, project, unity_version, ready, active, playing, compiling, updating,
//                   error, rejected_request, updated_utc, ...}
//   <id>/request.json : request claimed by the gate (moved atomically)
//   <id>/result.json  : terminal result {ok, status, id, suite, result, error, started_utc,
//                   finished_utc}; project methods may add their own evidence files here.
//   rejected-*.json   : rejected requests (invalid/duplicate id/suite) + error.
//
// Invoke signatures (public static): (), (string runDirectory), (string[] args),
// (string runDirectory, string[] args). Return value/ToString is stored in result.json.
// Optional <root>/allowlist.json = {"methods":["Namespace.Type.Method", ...]} limits invoke
// targets; without it every project static method is callable, so review before use.
// Domain reloads are handled: a run that was active before reload is marked failed instead
// of being silently forgotten.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;

namespace UnityAiEnvironment
{
    [InitializeOnLoad]
    internal static class UnityEditorGate
    {
        private const string SchemaVersion = "1";
        private const string GateFolder = "Temp/UnityEditorGate";
        private static readonly string Project;
        private static readonly int ProcessId;
        private static readonly string Root;
        private static readonly Regex IdPattern = new Regex("^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
            RegexOptions.CultureInvariant);
        private static readonly HashSet<string> Suites = new HashSet<string>(StringComparer.Ordinal)
        {
            "refresh", "wait-compile", "invoke",
        };

        private static Run active;
        private static double nextPoll;
        private static string lastStatus;
        private static bool lastReady;
        private static bool lastPlaying;

#pragma warning disable 0649 // Request/Receipt/Rejected/Allowlist fields are filled by JsonUtility.

        [Serializable]
        private sealed class Request
        {
            public int schema_version;
            public string id;
            public string suite;
            public string type;
            public string method;
            public string[] args;
            public string note;
        }

        [Serializable]
        private sealed class Receipt
        {
            public int schema_version = 1;
            public string status;
            public bool ok;
            public string id;
            public string suite;
            public int pid;
            public string project;
            public string unity_version;
            public bool ready;
            public bool active;
            public bool playing;
            public bool compiling;
            public bool updating;
            public string updated_utc;
            public string started_utc;
            public string finished_utc;
            public string error;
            public string rejected_request;
            public string result;
        }

        [Serializable]
        private sealed class Rejected
        {
            public int schema_version = 1;
            public string id;
            public string error;
            public string raw;
            public string rejected_utc;
        }

        [Serializable]
        private sealed class Allowlist
        {
            public string[] methods;
        }

#pragma warning restore 0649

        private sealed class Run
        {
            public Request request;
            public string directory;
            public string startedUtc;
            public string stage;
        }

        static UnityEditorGate()
        {
            ProcessId = System.Diagnostics.Process.GetCurrentProcess().Id;
            Project = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
            Root = Path.GetFullPath(Path.Combine(Project, GateFolder,
                ProcessId.ToString(CultureInfo.InvariantCulture)));
            try
            {
                Directory.CreateDirectory(Root);
                RecoverInterruptedRun();
                EditorApplication.update += Poll;
                WriteStatus(NewReceipt(null, "ready"));
            }
            catch (Exception error)
            {
                Debug.LogException(error);
            }
        }

        private static bool HardBusy => EditorApplication.isCompiling || EditorApplication.isUpdating;
        private static bool TransitionBusy => EditorApplication.isPlayingOrWillChangePlaymode &&
                                              !EditorApplication.isPlaying;
        private static bool ReadyToAccept => !HardBusy && !TransitionBusy && active == null;

        private static void RecoverInterruptedRun()
        {
            string path = Path.Combine(Root, "status.json");
            if (!File.Exists(path))
                return;
            Receipt previous = ReadJson<Receipt>(path);
            if (previous == null || !previous.active && string.CompareOrdinal(previous.status, "started") != 0)
                return;
            Receipt receipt = NewReceipt(previous.id, "failed");
            receipt.ok = false;
            receipt.suite = previous.suite;
            receipt.started_utc = previous.started_utc;
            receipt.finished_utc = Now();
            receipt.error = "Interrupted by script domain reload; rerun with a new request id.";
            WriteStatus(receipt);
            if (!string.IsNullOrEmpty(previous.id))
            {
                string runDirectory = CheckedPath(Path.Combine(Root, previous.id));
                if (Directory.Exists(runDirectory))
                    WriteRunResult(runDirectory, receipt);
            }
        }

        private static void Poll()
        {
            if (EditorApplication.timeSinceStartup < nextPoll)
                return;
            nextPoll = EditorApplication.timeSinceStartup + 0.5;
            try
            {
                if (active != null)
                {
                    StepActive();
                    return;
                }
                if (!ReadyToAccept)
                {
                    PublishIdle();
                    return;
                }
                string requestPath = Path.Combine(Root, "request.json");
                if (!File.Exists(requestPath))
                {
                    PublishIdle();
                    return;
                }
                StartRequest(requestPath);
            }
            catch (Exception error)
            {
                Debug.LogException(error);
                try
                {
                    Receipt receipt = NewReceipt(active != null ? active.request.id : null, "failed");
                    receipt.ok = false;
                    receipt.error = "Gate loop error: " + error;
                    WriteStatus(receipt);
                }
                catch (Exception inner)
                {
                    Debug.LogException(inner);
                }
                active = null;
            }
        }

        private static void PublishIdle()
        {
            bool ready = ReadyToAccept;
            if (ready == lastReady && (ready ? "ready" : "busy") == lastStatus &&
                EditorApplication.isPlaying == lastPlaying)
                return;
            lastReady = ready;
            lastPlaying = EditorApplication.isPlaying;
            WriteStatus(NewReceipt(null, ready ? "ready" : "busy"));
        }

        private static Receipt NewReceipt(string id, string status)
        {
            return new Receipt
            {
                schema_version = 1,
                status = status,
                ok = status != "failed",
                id = id ?? "",
                suite = "",
                pid = ProcessId,
                project = Project,
                unity_version = Application.unityVersion,
                ready = status == "ready",
                active = status == "started",
                playing = EditorApplication.isPlaying,
                compiling = EditorApplication.isCompiling,
                updating = EditorApplication.isUpdating,
                updated_utc = Now(),
                started_utc = "",
                finished_utc = "",
                error = "",
                rejected_request = "",
                result = "",
            };
        }

        private static void StartRequest(string requestPath)
        {
            string text;
            try
            {
                text = File.ReadAllText(requestPath, Encoding.UTF8);
            }
            catch (Exception error)
            {
                Reject(requestPath, null, "Cannot read request.json: " + error.Message, "");
                return;
            }
            Request request;
            try
            {
                request = JsonUtility.FromJson<Request>(text);
            }
            catch (Exception error)
            {
                Reject(requestPath, null, "Invalid request JSON: " + error.Message, text);
                return;
            }
            string errorMessage = ValidateRequest(request);
            if (errorMessage != null)
            {
                Reject(requestPath, request, errorMessage, text);
                return;
            }
            string runDirectory = CheckedPath(Path.Combine(Root, request.id));
            if (Directory.Exists(runDirectory) || File.Exists(runDirectory))
            {
                Reject(requestPath, request, "Request id already has evidence; ids are immutable: " + request.id, text);
                return;
            }
            Directory.CreateDirectory(runDirectory);
            File.Move(requestPath, CheckedPath(Path.Combine(runDirectory, "request.json")));
            active = new Run
            {
                request = request,
                directory = runDirectory,
                startedUtc = Now(),
                stage = string.Equals(request.suite, "invoke", StringComparison.Ordinal) ? "invoke" : request.suite,
            };
            Receipt receipt = NewReceipt(request.id, "started");
            receipt.suite = request.suite;
            receipt.started_utc = active.startedUtc;
            WriteStatus(receipt);
            StepActive();
        }

        private static string ValidateRequest(Request request)
        {
            if (request == null)
                return "Empty request";
            if (request.schema_version != 1)
                return "Unsupported schema_version: " + request.schema_version;
            if (string.IsNullOrEmpty(request.id) || !IdPattern.IsMatch(request.id))
                return "Request id must be 1-64 ASCII characters [A-Za-z0-9._-], starting with a letter or digit";
            if (string.IsNullOrEmpty(request.suite) || !Suites.Contains(request.suite))
                return "Unsupported suite: " + request.suite;
            if (string.Equals(request.suite, "invoke", StringComparison.Ordinal))
            {
                if (string.IsNullOrEmpty(request.type) || string.IsNullOrEmpty(request.method))
                    return "suite=invoke requires type and method";
                string allowed = CheckAllowlist(request.type, request.method);
                if (allowed != null)
                    return allowed;
            }
            return null;
        }

        private static string CheckAllowlist(string type, string method)
        {
            string path = Path.Combine(Root, "allowlist.json");
            if (!File.Exists(path))
                return null;
            Allowlist allowlist;
            try
            {
                allowlist = JsonUtility.FromJson<Allowlist>(File.ReadAllText(path, Encoding.UTF8));
            }
            catch (Exception error)
            {
                return "allowlist.json is invalid: " + error.Message;
            }
            if (allowlist == null || allowlist.methods == null || allowlist.methods.Length == 0)
                return "allowlist.json exists but lists no methods; invoke is disabled";
            string wanted = type + "." + method;
            foreach (string entry in allowlist.methods)
            {
                if (string.Equals(entry, wanted, StringComparison.Ordinal))
                    return null;
            }
            return "Method is not in allowlist.json: " + wanted;
        }

        private static void StepActive()
        {
            if (active == null)
                return;
            if (string.Equals(active.stage, "refresh", StringComparison.Ordinal))
            {
                if (HardBusy || TransitionBusy)
                    return;
                AssetDatabase.Refresh(ImportAssetOptions.ForceUpdate);
                active.stage = "wait-compile";
                return;
            }
            if (string.Equals(active.stage, "wait-compile", StringComparison.Ordinal))
            {
                if (HardBusy)
                    return;
                Finish(true, "Assets refreshed; compile/import completed.");
                return;
            }
            if (HardBusy)
                return;
            RunInvoke();
        }

        private static void RunInvoke()
        {
            Request request = active.request;
            MethodInfo method;
            try
            {
                method = FindMethod(request.type, request.method);
            }
            catch (Exception error)
            {
                Finish(false, "Cannot resolve method: " + error.Message);
                return;
            }
            object[] parameters;
            try
            {
                parameters = BuildParameters(method, active.directory, request.args);
            }
            catch (Exception error)
            {
                Finish(false, "Unsupported invoke signature: " + error.Message);
                return;
            }
            try
            {
                object value = method.Invoke(null, parameters);
                Finish(true, value == null ? "" : value.ToString());
            }
            catch (TargetInvocationException error)
            {
                Exception inner = error.InnerException ?? error;
                Finish(false, inner.GetType().Name + ": " + inner.Message + "\n" + inner.StackTrace);
            }
            catch (Exception error)
            {
                Finish(false, error.GetType().Name + ": " + error.Message);
            }
        }

        private static MethodInfo FindMethod(string typeName, string methodName)
        {
            Type type = Type.GetType(typeName, false);
            if (type == null)
            {
                foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
                {
                    type = assembly.GetType(typeName, false);
                    if (type != null)
                        break;
                }
            }
            if (type == null)
                throw new InvalidOperationException("Type not found: " + typeName);
            MethodInfo method = type.GetMethod(methodName, BindingFlags.Public | BindingFlags.Static);
            if (method == null)
                throw new InvalidOperationException("Public static method not found: " + typeName + "." + methodName);
            if (method.IsAbstract || method.ContainsGenericParameters)
                throw new InvalidOperationException("Method must be concrete and non-generic: " + typeName + "." + methodName);
            return method;
        }

        private static object[] BuildParameters(MethodInfo method, string runDirectory, string[] args)
        {
            ParameterInfo[] parameters = method.GetParameters();
            string[] safeArgs = args ?? new string[0];
            if (parameters.Length == 0)
                return null;
            if (parameters.Length == 1)
            {
                if (parameters[0].ParameterType == typeof(string))
                    return new object[] { runDirectory };
                if (parameters[0].ParameterType == typeof(string[]))
                    return new object[] { safeArgs };
            }
            if (parameters.Length == 2 && parameters[0].ParameterType == typeof(string) &&
                parameters[1].ParameterType == typeof(string[]))
                return new object[] { runDirectory, safeArgs };
            throw new InvalidOperationException("Use (), (string runDirectory), (string[] args) or " +
                                                "(string runDirectory, string[] args); got " +
                                                parameters.Length + " parameter(s)");
        }

        private static void Finish(bool ok, string result)
        {
            Run finished = active;
            active = null;
            string finishedUtc = Now();
            Receipt receipt = NewReceipt(finished.request.id, ok ? "observed" : "failed");
            receipt.ok = ok;
            receipt.suite = finished.request.suite;
            receipt.started_utc = finished.startedUtc;
            receipt.finished_utc = finishedUtc;
            receipt.ready = false;
            receipt.active = false;
            receipt.result = result ?? "";
            receipt.error = ok ? "" : (result ?? "");
            WriteStatus(receipt);
            WriteRunResult(finished.directory, receipt);
        }

        private static void WriteRunResult(string runDirectory, Receipt receipt)
        {
            Receipt result = new Receipt
            {
                schema_version = 1,
                status = receipt.status,
                ok = receipt.ok,
                id = receipt.id,
                suite = receipt.suite,
                pid = receipt.pid,
                project = receipt.project,
                unity_version = receipt.unity_version,
                ready = false,
                active = false,
                playing = receipt.playing,
                compiling = receipt.compiling,
                updating = receipt.updating,
                updated_utc = receipt.updated_utc,
                started_utc = receipt.started_utc,
                finished_utc = receipt.finished_utc,
                error = receipt.error,
                rejected_request = "",
                result = receipt.result,
            };
            WriteJson(Path.Combine(runDirectory, "result.json"), result);
        }

        private static void Reject(string requestPath, Request request, string message, string raw)
        {
            string stamp = DateTime.UtcNow.ToString("yyyyMMddTHHmmssfffZ", CultureInfo.InvariantCulture);
            string rejectedPath = Path.Combine(Root, "rejected-" + stamp + ".json");
            Rejected rejected = new Rejected
            {
                schema_version = 1,
                id = request != null ? request.id : "",
                error = message,
                raw = raw != null && raw.Length > 4000 ? raw.Substring(0, 4000) : raw,
                rejected_utc = Now(),
            };
            try
            {
                WriteJson(rejectedPath, rejected);
                if (File.Exists(requestPath))
                    File.Delete(requestPath);
            }
            catch (Exception error)
            {
                Debug.LogException(error);
            }
            Receipt receipt = NewReceipt(request != null ? request.id : null, "ready");
            receipt.rejected_request = Path.GetFileName(rejectedPath);
            receipt.error = message;
            WriteStatus(receipt);
        }

        private static void WriteStatus(Receipt receipt)
        {
            receipt.updated_utc = Now();
            lastStatus = receipt.status;
            lastReady = receipt.ready;
            lastPlaying = EditorApplication.isPlaying;
            WriteJson(Path.Combine(Root, "status.json"), receipt);
        }

        private static void WriteJson(string path, object value)
        {
            string text = JsonUtility.ToJson(value, true) + "\n";
            string tmp = path + ".tmp";
            File.WriteAllText(tmp, text, new UTF8Encoding(false));
            if (File.Exists(path))
            {
                File.Delete(path);
            }
            File.Move(tmp, path);
        }

        private static T ReadJson<T>(string path) where T : class
        {
            try
            {
                return JsonUtility.FromJson<T>(File.ReadAllText(path, Encoding.UTF8));
            }
            catch (Exception)
            {
                return null;
            }
        }

        private static string CheckedPath(string path)
        {
            string full = Path.GetFullPath(path);
            string prefix = Root.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) +
                            Path.DirectorySeparatorChar;
            StringComparison comparison = Application.platform == RuntimePlatform.WindowsEditor
                ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
            if (!full.StartsWith(prefix, comparison) && !string.Equals(full.TrimEnd(Path.DirectorySeparatorChar),
                    Root.TrimEnd(Path.DirectorySeparatorChar), comparison))
                throw new InvalidOperationException("Path escapes the gate root: " + full);
            return full;
        }

        private static string Now()
        {
            return DateTime.UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ", CultureInfo.InvariantCulture);
        }
    }
}
