// \0rolldown/runtime.js
var e = (e, t) => () => (t || (e((t = { exports: {} }).exports, t, t.exports), e = null), t.exports), t = /* @__PURE__ */ e(((e) => {
	function t(e, t) {
		var n = e.length;
		e.push(t);
		a: for (; 0 < n;) {
			var r = n - 1 >>> 1, a = e[r];
			if (0 < i(a, t)) e[r] = t, e[n] = a, n = r;
			else break a;
		}
	}
	function n(e) {
		return e.length === 0 ? null : e[0];
	}
	function r(e) {
		if (e.length === 0) return null;
		var t = e[0], n = e.pop();
		if (n !== t) {
			e[0] = n;
			a: for (var r = 0, a = e.length, o = a >>> 1; r < o;) {
				var s = 2 * (r + 1) - 1, c = e[s], l = s + 1, u = e[l];
				if (0 > i(c, n)) l < a && 0 > i(u, c) ? (e[r] = u, e[l] = n, r = l) : (e[r] = c, e[s] = n, r = s);
				else if (l < a && 0 > i(u, n)) e[r] = u, e[l] = n, r = l;
				else break a;
			}
		}
		return t;
	}
	function i(e, t) {
		var n = e.sortIndex - t.sortIndex;
		return n === 0 ? e.id - t.id : n;
	}
	if (e.unstable_now = void 0, typeof performance == "object" && typeof performance.now == "function") {
		var a = performance;
		e.unstable_now = function() {
			return a.now();
		};
	} else {
		var o = Date, s = o.now();
		e.unstable_now = function() {
			return o.now() - s;
		};
	}
	var c = [], l = [], u = 1, d = null, f = 3, p = !1, m = !1, h = !1, g = !1, _ = typeof setTimeout == "function" ? setTimeout : null, v = typeof clearTimeout == "function" ? clearTimeout : null, y = typeof setImmediate < "u" ? setImmediate : null;
	function b(e) {
		for (var i = n(l); i !== null;) {
			if (i.callback === null) r(l);
			else if (i.startTime <= e) r(l), i.sortIndex = i.expirationTime, t(c, i);
			else break;
			i = n(l);
		}
	}
	function ee(e) {
		if (h = !1, b(e), !m) {
			if (n(c) !== null) m = !0, x || (x = !0, ne());
			else {
				var t = n(l);
				t !== null && E(ee, t.startTime - e);
			}
		}
	}
	var x = !1, te = -1, S = 5, C = -1;
	function w() {
		return g ? !0 : !(e.unstable_now() - C < S);
	}
	function T() {
		if (g = !1, x) {
			var t = e.unstable_now();
			C = t;
			var i = !0;
			try {
				a: {
					m = !1, h && (h = !1, v(te), te = -1), p = !0;
					var a = f;
					try {
						b: {
							for (b(t), d = n(c); d !== null && !(d.expirationTime > t && w());) {
								var o = d.callback;
								if (typeof o == "function") {
									d.callback = null, f = d.priorityLevel;
									var s = o(d.expirationTime <= t);
									if (t = e.unstable_now(), typeof s == "function") {
										d.callback = s, b(t), i = !0;
										break b;
									}
									d === n(c) && r(c), b(t);
								} else r(c);
								d = n(c);
							}
							if (d !== null) i = !0;
							else {
								var u = n(l);
								u !== null && E(ee, u.startTime - t), i = !1;
							}
						}
						break a;
					} finally {
						d = null, f = a, p = !1;
					}
					i = void 0;
				}
			} finally {
				i ? ne() : x = !1;
			}
		}
	}
	var ne;
	if (typeof y == "function") ne = function() {
		y(T);
	};
	else if (typeof MessageChannel < "u") {
		var re = new MessageChannel(), ie = re.port2;
		re.port1.onmessage = T, ne = function() {
			ie.postMessage(null);
		};
	} else ne = function() {
		_(T, 0);
	};
	function E(t, n) {
		te = _(function() {
			t(e.unstable_now());
		}, n);
	}
	e.unstable_IdlePriority = 5, e.unstable_ImmediatePriority = 1, e.unstable_LowPriority = 4, e.unstable_NormalPriority = 3, e.unstable_Profiling = null, e.unstable_UserBlockingPriority = 2, e.unstable_cancelCallback = function(e) {
		e.callback = null;
	}, e.unstable_forceFrameRate = function(e) {
		0 > e || 125 < e ? console.error("forceFrameRate takes a positive int between 0 and 125, forcing frame rates higher than 125 fps is not supported") : S = 0 < e ? Math.floor(1e3 / e) : 5;
	}, e.unstable_getCurrentPriorityLevel = function() {
		return f;
	}, e.unstable_next = function(e) {
		switch (f) {
			case 1:
			case 2:
			case 3:
				var t = 3;
				break;
			default: t = f;
		}
		var n = f;
		f = t;
		try {
			return e();
		} finally {
			f = n;
		}
	}, e.unstable_requestPaint = function() {
		g = !0;
	}, e.unstable_runWithPriority = function(e, t) {
		switch (e) {
			case 1:
			case 2:
			case 3:
			case 4:
			case 5: break;
			default: e = 3;
		}
		var n = f;
		f = e;
		try {
			return t();
		} finally {
			f = n;
		}
	}, e.unstable_scheduleCallback = function(r, i, a) {
		var o = e.unstable_now();
		switch (typeof a == "object" && a ? (a = a.delay, a = typeof a == "number" && 0 < a ? o + a : o) : a = o, r) {
			case 1:
				var s = -1;
				break;
			case 2:
				s = 250;
				break;
			case 5:
				s = 1073741823;
				break;
			case 4:
				s = 1e4;
				break;
			default: s = 5e3;
		}
		return s = a + s, r = {
			id: u++,
			callback: i,
			priorityLevel: r,
			startTime: a,
			expirationTime: s,
			sortIndex: -1
		}, a > o ? (r.sortIndex = a, t(l, r), n(c) === null && r === n(l) && (h ? (v(te), te = -1) : h = !0, E(ee, a - o))) : (r.sortIndex = s, t(c, r), m || p || (m = !0, x || (x = !0, ne()))), r;
	}, e.unstable_shouldYield = w, e.unstable_wrapCallback = function(e) {
		var t = f;
		return function() {
			var n = f;
			f = t;
			try {
				return e.apply(this, arguments);
			} finally {
				f = n;
			}
		};
	};
})), n = /* @__PURE__ */ e(((e, n) => {
	n.exports = t();
})), r = /* @__PURE__ */ e(((e) => {
	var t = Symbol.for("react.transitional.element"), n = Symbol.for("react.portal"), r = Symbol.for("react.fragment"), i = Symbol.for("react.strict_mode"), a = Symbol.for("react.profiler"), o = Symbol.for("react.consumer"), s = Symbol.for("react.context"), c = Symbol.for("react.forward_ref"), l = Symbol.for("react.suspense"), u = Symbol.for("react.memo"), d = Symbol.for("react.lazy"), f = Symbol.for("react.activity"), p = Symbol.for("react.view_transition"), m = Symbol.iterator;
	function h(e) {
		return typeof e != "object" || !e ? null : (e = m && e[m] || e["@@iterator"], typeof e == "function" ? e : null);
	}
	var g = {
		isMounted: function() {
			return !1;
		},
		enqueueForceUpdate: function() {},
		enqueueReplaceState: function() {},
		enqueueSetState: function() {}
	}, _ = Object.assign, v = {};
	function y(e, t, n) {
		this.props = e, this.context = t, this.refs = v, this.updater = n || g;
	}
	y.prototype.isReactComponent = {}, y.prototype.setState = function(e, t) {
		if (typeof e != "object" && typeof e != "function" && e != null) throw Error("takes an object of state variables to update or a function which returns an object of state variables.");
		this.updater.enqueueSetState(this, e, t, "setState");
	}, y.prototype.forceUpdate = function(e) {
		this.updater.enqueueForceUpdate(this, e, "forceUpdate");
	};
	function b() {}
	b.prototype = y.prototype;
	function ee(e, t, n) {
		this.props = e, this.context = t, this.refs = v, this.updater = n || g;
	}
	var x = ee.prototype = new b();
	x.constructor = ee, _(x, y.prototype), x.isPureReactComponent = !0;
	var te = Array.isArray;
	function S() {}
	var C = {
		H: null,
		A: null,
		T: null,
		S: null
	}, w = Object.prototype.hasOwnProperty;
	function T(e, n, r) {
		var i = r.ref;
		return {
			$$typeof: t,
			type: e,
			key: n,
			ref: i === void 0 ? null : i,
			props: r
		};
	}
	function ne(e, t) {
		return T(e.type, t, e.props);
	}
	function re(e) {
		return typeof e == "object" && !!e && e.$$typeof === t;
	}
	function ie(e) {
		var t = {
			"=": "=0",
			":": "=2"
		};
		return "$" + e.replace(/[=:]/g, function(e) {
			return t[e];
		});
	}
	var E = /\/+/g;
	function ae(e, t) {
		return typeof e == "object" && e && e.key != null ? ie("" + e.key) : t.toString(36);
	}
	function oe(e) {
		switch (e.status) {
			case "fulfilled": return e.value;
			case "rejected": throw e.reason;
			default: switch (typeof e.status == "string" ? e.then(S, S) : (e.status = "pending", e.then(function(t) {
				e.status === "pending" && (e.status = "fulfilled", e.value = t);
			}, function(t) {
				e.status === "pending" && (e.status = "rejected", e.reason = t);
			})), e.status) {
				case "fulfilled": return e.value;
				case "rejected": throw e.reason;
			}
		}
		throw e;
	}
	function se(e, r, i, a, o) {
		var s = typeof e;
		(s === "undefined" || s === "boolean") && (e = null);
		var c = !1;
		if (e === null) c = !0;
		else switch (s) {
			case "bigint":
			case "string":
			case "number":
				c = !0;
				break;
			case "object": switch (e.$$typeof) {
				case t:
				case n:
					c = !0;
					break;
				case d: return c = e._init, se(c(e._payload), r, i, a, o);
			}
		}
		if (c) return o = o(e), c = a === "" ? "." + ae(e, 0) : a, te(o) ? (i = "", c != null && (i = c.replace(E, "$&/") + "/"), se(o, r, i, "", function(e) {
			return e;
		})) : o != null && (re(o) && (o = ne(o, i + (o.key == null || e && e.key === o.key ? "" : ("" + o.key).replace(E, "$&/") + "/") + c)), r.push(o)), 1;
		c = 0;
		var l = a === "" ? "." : a + ":";
		if (te(e)) for (var u = 0; u < e.length; u++) a = e[u], s = l + ae(a, u), c += se(a, r, i, s, o);
		else if (u = h(e), typeof u == "function") for (e = u.call(e), u = 0; !(a = e.next()).done;) a = a.value, s = l + ae(a, u++), c += se(a, r, i, s, o);
		else if (s === "object") {
			if (typeof e.then == "function") return se(oe(e), r, i, a, o);
			throw r = String(e), Error("Objects are not valid as a React child (found: " + (r === "[object Object]" ? "object with keys {" + Object.keys(e).join(", ") + "}" : r) + "). If you meant to render a collection of children, use an array instead.");
		}
		return c;
	}
	function D(e, t, n) {
		if (e == null) return e;
		var r = [], i = 0;
		return se(e, r, "", "", function(e) {
			return t.call(n, e, i++);
		}), r;
	}
	function ce(e) {
		if (e._status === -1) {
			var t = e._result, n = t();
			n.then(function(t) {
				(e._status === 0 || e._status === -1) && (e._status = 1, e._result = t, n.status === void 0 && (n.status = "fulfilled", n.value = t));
			}, function(t) {
				(e._status === 0 || e._status === -1) && (e._status = 2, e._result = t, n.status === void 0 && (n.status = "rejected", n.reason = t));
			}), e._status === -1 && (e._status = 0, e._result = n);
		}
		if (e._status === 1) return e._result.default;
		throw e._result;
	}
	var le = typeof reportError == "function" ? reportError : function(e) {
		if (typeof window == "object" && typeof window.ErrorEvent == "function") {
			var t = new window.ErrorEvent("error", {
				bubbles: !0,
				cancelable: !0,
				message: typeof e == "object" && e && typeof e.message == "string" ? String(e.message) : String(e),
				error: e
			});
			if (!window.dispatchEvent(t)) return;
		} else if (typeof process == "object" && typeof process.emit == "function") {
			process.emit("uncaughtException", e);
			return;
		}
		console.error(e);
	};
	function O(e) {
		var t = C.T, n = {};
		n.types = t === null ? null : t.types, C.T = n;
		try {
			var r = e(), i = C.S;
			i !== null && i(n, r), typeof r == "object" && r && typeof r.then == "function" && r.then(S, le);
		} catch (e) {
			le(e);
		} finally {
			t !== null && n.types !== null && (t.types = n.types), C.T = t;
		}
	}
	function ue(e) {
		var t = C.T;
		if (t !== null) {
			var n = t.types;
			n === null ? t.types = [e] : n.indexOf(e) === -1 && n.push(e);
		} else O(ue.bind(null, e));
	}
	var de = {
		map: D,
		forEach: function(e, t, n) {
			D(e, function() {
				t.apply(this, arguments);
			}, n);
		},
		count: function(e) {
			var t = 0;
			return D(e, function() {
				t++;
			}), t;
		},
		toArray: function(e) {
			return D(e, function(e) {
				return e;
			}) || [];
		},
		only: function(e) {
			if (!re(e)) throw Error("React.Children.only expected to receive a single React element child.");
			return e;
		}
	};
	e.Activity = f, e.Children = de, e.Component = y, e.Fragment = r, e.Profiler = a, e.PureComponent = ee, e.StrictMode = i, e.Suspense = l, e.ViewTransition = p, e.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE = C, e.__COMPILER_RUNTIME = {
		__proto__: null,
		c: function(e) {
			return C.H.useMemoCache(e);
		}
	}, e.addTransitionType = ue, e.cache = function(e) {
		return function() {
			return e.apply(null, arguments);
		};
	}, e.cacheSignal = function() {
		return null;
	}, e.cloneElement = function(e, t, n) {
		if (e == null) throw Error("The argument must be a React element, but you passed " + e + ".");
		var r = _({}, e.props), i = e.key;
		if (t != null) for (a in t.key !== void 0 && (i = "" + t.key), t) !w.call(t, a) || a === "key" || a === "__self" || a === "__source" || a === "ref" && t.ref === void 0 || (r[a] = t[a]);
		var a = arguments.length - 2;
		if (a === 1) r.children = n;
		else if (1 < a) {
			for (var o = Array(a), s = 0; s < a; s++) o[s] = arguments[s + 2];
			r.children = o;
		}
		return T(e.type, i, r);
	}, e.createContext = function(e) {
		return e = {
			$$typeof: s,
			_currentValue: e,
			_currentValue2: e,
			_threadCount: 0,
			Provider: null,
			Consumer: null
		}, e.Provider = e, e.Consumer = {
			$$typeof: o,
			_context: e
		}, e;
	}, e.createElement = function(e, t, n) {
		var r, i = {}, a = null;
		if (t != null) for (r in t.key !== void 0 && (a = "" + t.key), t) w.call(t, r) && r !== "key" && r !== "__self" && r !== "__source" && (i[r] = t[r]);
		var o = arguments.length - 2;
		if (o === 1) i.children = n;
		else if (1 < o) {
			for (var s = Array(o), c = 0; c < o; c++) s[c] = arguments[c + 2];
			i.children = s;
		}
		if (e && e.defaultProps) for (r in o = e.defaultProps, o) i[r] === void 0 && (i[r] = o[r]);
		return T(e, a, i);
	}, e.createRef = function() {
		return { current: null };
	}, e.forwardRef = function(e) {
		return {
			$$typeof: c,
			render: e
		};
	}, e.isValidElement = re, e.lazy = function(e) {
		return {
			$$typeof: d,
			_payload: {
				_status: -1,
				_result: e
			},
			_init: ce
		};
	}, e.memo = function(e, t) {
		return {
			$$typeof: u,
			type: e,
			compare: t === void 0 ? null : t
		};
	}, e.startTransition = O, e.unstable_useCacheRefresh = function() {
		return C.H.useCacheRefresh();
	}, e.use = function(e) {
		return C.H.use(e);
	}, e.useActionState = function(e, t, n) {
		return C.H.useActionState(e, t, n);
	}, e.useCallback = function(e, t) {
		return C.H.useCallback(e, t);
	}, e.useContext = function(e) {
		return C.H.useContext(e);
	}, e.useDebugValue = function() {}, e.useDeferredValue = function(e, t) {
		return C.H.useDeferredValue(e, t);
	}, e.useEffect = function(e, t) {
		return C.H.useEffect(e, t);
	}, e.useEffectEvent = function(e) {
		return C.H.useEffectEvent(e);
	}, e.useId = function() {
		return C.H.useId();
	}, e.useImperativeHandle = function(e, t, n) {
		return C.H.useImperativeHandle(e, t, n);
	}, e.useInsertionEffect = function(e, t) {
		return C.H.useInsertionEffect(e, t);
	}, e.useLayoutEffect = function(e, t) {
		return C.H.useLayoutEffect(e, t);
	}, e.useMemo = function(e, t) {
		return C.H.useMemo(e, t);
	}, e.useOptimistic = function(e, t) {
		return C.H.useOptimistic(e, t);
	}, e.useReducer = function(e, t, n) {
		return C.H.useReducer(e, t, n);
	}, e.useRef = function(e) {
		return C.H.useRef(e);
	}, e.useState = function(e) {
		return C.H.useState(e);
	}, e.useSyncExternalStore = function(e, t, n) {
		return C.H.useSyncExternalStore(e, t, n);
	}, e.useTransition = function() {
		return C.H.useTransition();
	}, e.version = "19.3.1";
})), i = /* @__PURE__ */ e(((e, t) => {
	t.exports = r();
})), a = /* @__PURE__ */ e(((e) => {
	var t = i();
	function n(e) {
		var t = "https://react.dev/errors/" + e;
		if (1 < arguments.length) {
			t += "?args[]=" + encodeURIComponent(arguments[1]);
			for (var n = 2; n < arguments.length; n++) t += "&args[]=" + encodeURIComponent(arguments[n]);
		}
		return "Minified React error #" + e + "; visit " + t + " for the full message or use the non-minified dev environment for full errors and additional helpful warnings.";
	}
	function r() {}
	var a = {
		d: {
			f: r,
			r: function() {
				throw Error(n(522));
			},
			D: r,
			C: r,
			L: r,
			m: r,
			X: r,
			S: r,
			M: r
		},
		p: 0,
		findDOMNode: null
	}, o = Symbol.for("react.portal"), s = Symbol.for("react.recoverable"), c = Symbol.for("react.optimistic_key");
	function l(e, t, n) {
		var r = 3 < arguments.length && arguments[3] !== void 0 ? arguments[3] : null;
		return {
			$$typeof: o,
			key: r == null ? null : r === c ? c : "" + r,
			children: e,
			containerInfo: t,
			implementation: n
		};
	}
	var u = t.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE;
	function d(e, t) {
		if (e === "font") return "";
		if (typeof t == "string") return t === "use-credentials" ? t : "";
	}
	e.__DOM_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE = a, e.browser = function(e) {
		return {
			$$typeof: s,
			_reason: e
		};
	}, e.createPortal = function(e, t) {
		var r = 2 < arguments.length && arguments[2] !== void 0 ? arguments[2] : null;
		if (!t || t.nodeType !== 1 && t.nodeType !== 9 && t.nodeType !== 11) throw Error(n(299));
		return l(e, t, null, r);
	}, e.flushSync = function(e) {
		var t = u.T, n = a.p;
		try {
			if (u.T = null, a.p = 2, e) return e();
		} finally {
			u.T = t, a.p = n, a.d.f();
		}
	}, e.preconnect = function(e, t) {
		typeof e == "string" && (t ? (t = t.crossOrigin, t = typeof t == "string" ? t === "use-credentials" ? t : "" : void 0) : t = null, a.d.C(e, t));
	}, e.prefetchDNS = function(e) {
		typeof e == "string" && a.d.D(e);
	}, e.preinit = function(e, t) {
		if (typeof e == "string" && t && typeof t.as == "string") {
			var n = t.as, r = d(n, t.crossOrigin), i = typeof t.integrity == "string" ? t.integrity : void 0, o = typeof t.fetchPriority == "string" ? t.fetchPriority : void 0;
			n === "style" ? a.d.S(e, typeof t.precedence == "string" ? t.precedence : void 0, {
				crossOrigin: r,
				integrity: i,
				fetchPriority: o
			}) : n === "script" && a.d.X(e, {
				crossOrigin: r,
				integrity: i,
				fetchPriority: o,
				nonce: typeof t.nonce == "string" ? t.nonce : void 0
			});
		}
	}, e.preinitModule = function(e, t) {
		if (typeof e == "string") {
			if (typeof t == "object" && t) {
				if (t.as == null || t.as === "script") {
					var n = d(t.as, t.crossOrigin);
					a.d.M(e, {
						crossOrigin: n,
						integrity: typeof t.integrity == "string" ? t.integrity : void 0,
						nonce: typeof t.nonce == "string" ? t.nonce : void 0,
						fetchPriority: typeof t.fetchPriority == "string" ? t.fetchPriority : void 0
					});
				}
			} else t ?? a.d.M(e);
		}
	}, e.preload = function(e, t) {
		if (typeof e == "string" && typeof t == "object" && t && typeof t.as == "string") {
			var n = t.as, r = d(n, t.crossOrigin);
			a.d.L(e, n, {
				crossOrigin: r,
				integrity: typeof t.integrity == "string" ? t.integrity : void 0,
				nonce: typeof t.nonce == "string" ? t.nonce : void 0,
				type: typeof t.type == "string" ? t.type : void 0,
				fetchPriority: typeof t.fetchPriority == "string" ? t.fetchPriority : void 0,
				referrerPolicy: typeof t.referrerPolicy == "string" ? t.referrerPolicy : void 0,
				imageSrcSet: typeof t.imageSrcSet == "string" ? t.imageSrcSet : void 0,
				imageSizes: typeof t.imageSizes == "string" ? t.imageSizes : void 0,
				media: typeof t.media == "string" ? t.media : void 0
			});
		}
	}, e.preloadModule = function(e, t) {
		if (typeof e == "string") {
			if (t) {
				var n = d(t.as, t.crossOrigin);
				a.d.m(e, {
					as: typeof t.as == "string" && t.as !== "script" ? t.as : void 0,
					crossOrigin: n,
					integrity: typeof t.integrity == "string" ? t.integrity : void 0,
					nonce: typeof t.nonce == "string" ? t.nonce : void 0,
					fetchPriority: typeof t.fetchPriority == "string" ? t.fetchPriority : void 0
				});
			} else a.d.m(e);
		}
	}, e.requestFormReset = function(e) {
		a.d.r(e);
	}, e.unstable_batchedUpdates = function(e, t) {
		return e(t);
	}, e.useFormState = function(e, t, n) {
		return u.H.useFormState(e, t, n);
	}, e.useFormStatus = function() {
		return u.H.useHostTransitionStatus();
	}, e.version = "19.3.1";
})), o = /* @__PURE__ */ e(((e, t) => {
	function n() {
		if (typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ < "u" && typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE == "function") try {
			__REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(n);
		} catch (e) {
			console.error(e);
		}
	}
	n(), t.exports = a();
})), s = /* @__PURE__ */ e(((e) => {
	var t = n(), r = i(), a = o();
	function s(e) {
		var t = "https://react.dev/errors/" + e;
		if (1 < arguments.length) {
			t += "?args[]=" + encodeURIComponent(arguments[1]);
			for (var n = 2; n < arguments.length; n++) t += "&args[]=" + encodeURIComponent(arguments[n]);
		}
		return "Minified React error #" + e + "; visit " + t + " for the full message or use the non-minified dev environment for full errors and additional helpful warnings.";
	}
	function c(e) {
		return !(!e || e.nodeType !== 1 && e.nodeType !== 9 && e.nodeType !== 11);
	}
	function l(e) {
		for (var t = e, n = t; n && !n.alternate;) t = n, t.flags & 4098 && (e = t.return), n = t.return;
		for (; t.return;) t = t.return;
		return t.tag === 3 ? e : null;
	}
	function u(e) {
		if (e.tag === 13) {
			var t = e.memoizedState;
			if (t === null && (e = e.alternate, e !== null && (t = e.memoizedState)), t !== null) return t.dehydrated;
		}
		return null;
	}
	function d(e) {
		if (e.tag === 31) {
			var t = e.memoizedState;
			if (t === null && (e = e.alternate, e !== null && (t = e.memoizedState)), t !== null) return t.dehydrated;
		}
		return null;
	}
	function f(e) {
		if (l(e) !== e) throw Error(s(188));
	}
	function p(e) {
		var t = e.alternate;
		if (!t) {
			if (t = l(e), t === null) throw Error(s(188));
			return t === e ? e : null;
		}
		for (var n = e, r = t;;) {
			var i = n.return;
			if (i === null) break;
			var a = i.alternate;
			if (a === null) {
				if (r = i.return, r !== null) {
					n = r;
					continue;
				}
				break;
			}
			if (i.child === a.child) {
				for (a = i.child; a;) {
					if (a === n) return f(i), e;
					if (a === r) return f(i), t;
					a = a.sibling;
				}
				throw Error(s(188));
			}
			if (n.return !== r.return) n = i, r = a;
			else {
				for (var o = !1, c = i.child; c;) {
					if (c === n) {
						o = !0, n = i, r = a;
						break;
					}
					if (c === r) {
						o = !0, r = i, n = a;
						break;
					}
					c = c.sibling;
				}
				if (!o) {
					for (c = a.child; c;) {
						if (c === n) {
							o = !0, n = a, r = i;
							break;
						}
						if (c === r) {
							o = !0, r = a, n = i;
							break;
						}
						c = c.sibling;
					}
					if (!o) throw Error(s(189));
				}
			}
			if (n.alternate !== r) throw Error(s(190));
		}
		if (n.tag !== 3) throw Error(s(188));
		return n.stateNode.current === n ? e : t;
	}
	function m(e) {
		var t = e.tag;
		if (t === 5 || t === 26 || t === 27 || t === 6) return e;
		for (e = e.child; e !== null;) {
			if (t = m(e), t !== null) return t;
			e = e.sibling;
		}
		return null;
	}
	function h(e, t, n, r, i, a) {
		for (; e !== null;) {
			if ((e.tag === 5 || e.tag === 27 || e.tag === 6) && n(e, r, i, a) || (e.tag !== 22 || e.memoizedState === null) && (t || e.tag !== 5 && e.tag !== 27) && h(e.child, t, n, r, i, a)) return !0;
			e = e.sibling;
		}
		return !1;
	}
	function g(e) {
		for (e = e.return; e !== null;) {
			if (e.tag === 3 || e.tag === 5 || e.tag === 27) return e;
			e = e.return;
		}
		return null;
	}
	function _(e) {
		var t = !1;
		for (e = e.return; e !== null && (e.tag === 4 && (t = !0), e.tag !== 3 && e.tag !== 5 && e.tag !== 27);) e = e.return;
		return t;
	}
	function v(e) {
		var t = [null, null], n = g(e);
		return n === null || y(t, e, n.child, { foundSelf: !1 }), t;
	}
	function y(e, t, n, r) {
		for (; n !== null;) {
			if (n === t) r.foundSelf = !0;
			else if (n.tag === 5 || n.tag === 27 || n.tag === 6) {
				if (r.foundSelf) return e[1] = n, !0;
				e[0] = n;
			} else if ((n.tag !== 22 || n.memoizedState === null) && y(e, t, n.child, r)) return !0;
			n = n.sibling;
		}
		return !1;
	}
	function b(e) {
		switch (e.tag) {
			case 5:
			case 27:
			case 6: return e.stateNode;
			case 3: return e.stateNode.containerInfo;
			default: throw Error(s(559));
		}
	}
	var ee = null, x = null;
	function te(e, t, n) {
		return e === n || e === t && (ee = e, !0);
	}
	function S(e, t, n) {
		return e === n ? (x = e, !1) : e === t && (x !== null && (ee = e), !0);
	}
	function C(e) {
		if (e === null) return null;
		do
			e = e === null ? null : e.return;
		while (e && e.tag !== 5 && e.tag !== 27 && e.tag !== 3);
		return e || null;
	}
	function w(e, t, n) {
		for (var r = 0, i = e; i; i = n(i)) r++;
		i = 0;
		for (var a = t; a; a = n(a)) i++;
		for (; 0 < r - i;) e = n(e), r--;
		for (; 0 < i - r;) t = n(t), i--;
		for (; r--;) {
			if (e === t || t !== null && e === t.alternate) return e;
			e = n(e), t = n(t);
		}
		return null;
	}
	var T = Object.assign, ne = Symbol.for("react.element"), re = Symbol.for("react.transitional.element"), ie = Symbol.for("react.portal"), E = Symbol.for("react.fragment"), ae = Symbol.for("react.strict_mode"), oe = Symbol.for("react.profiler"), se = Symbol.for("react.consumer"), D = Symbol.for("react.context"), ce = Symbol.for("react.forward_ref"), le = Symbol.for("react.suspense"), O = Symbol.for("react.suspense_list"), ue = Symbol.for("react.memo"), de = Symbol.for("react.lazy"), fe = Symbol.for("react.activity"), pe = Symbol.for("react.legacy_hidden"), me = Symbol.for("react.memo_cache_sentinel"), he = Symbol.for("react.view_transition"), ge = Symbol.for("react.recoverable"), _e = Symbol.iterator;
	function ve(e) {
		return typeof e != "object" || !e ? null : (e = _e && e[_e] || e["@@iterator"], typeof e == "function" ? e : null);
	}
	var ye = Symbol.for("react.client.reference");
	function be(e) {
		if (e == null) return null;
		if (typeof e == "function") return e.$$typeof === ye ? null : e.displayName || e.name || null;
		if (typeof e == "string") return e;
		switch (e) {
			case E: return "Fragment";
			case oe: return "Profiler";
			case ae: return "StrictMode";
			case le: return "Suspense";
			case O: return "SuspenseList";
			case fe: return "Activity";
			case he: return "ViewTransition";
		}
		if (typeof e == "object") switch (e.$$typeof) {
			case ie: return "Portal";
			case D: return e.displayName || "Context";
			case se: return (e._context.displayName || "Context") + ".Consumer";
			case ce:
				var t = e.render;
				return e = e.displayName, e ||= (e = t.displayName || t.name || "", e === "" ? "ForwardRef" : "ForwardRef(" + e + ")"), e;
			case ue: return t = e.displayName || null, t === null ? be(e.type) || "Memo" : t;
			case de:
				t = e._payload, e = e._init;
				try {
					return be(e(t));
				} catch {}
		}
		return null;
	}
	var xe = Array.isArray, k = r.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE, A = a.__DOM_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE, Se = {
		pending: !1,
		data: null,
		method: null,
		action: null
	}, Ce = [], we = -1;
	function Te(e) {
		return { current: e };
	}
	function Ee(e) {
		0 > we || (e.current = Ce[we], Ce[we] = null, we--);
	}
	function j(e, t) {
		we++, Ce[we] = e.current, e.current = t;
	}
	var De = Te(null), Oe = Te(null), ke = Te(null), Ae = Te(null);
	function je(e, t) {
		switch (j(ke, t), j(Oe, e), j(De, null), t.nodeType) {
			case 9:
			case 11:
				e = (e = t.documentElement) && (e = e.namespaceURI) ? up(e) : 0;
				break;
			default: if (e = t.tagName, t = t.namespaceURI) t = up(t), e = dp(t, e);
			else switch (e) {
				case "svg":
					e = 1;
					break;
				case "math":
					e = 2;
					break;
				default: e = 0;
			}
		}
		Ee(De), j(De, e);
	}
	function Me() {
		Ee(De), Ee(Oe), Ee(ke);
	}
	function Ne(e) {
		var t = e.memoizedState;
		t !== null && (sh._currentValue = t.memoizedState, j(Ae, e)), t = De.current;
		var n = dp(t, e.type);
		t !== n && (j(Oe, e), j(De, n));
	}
	function Pe(e) {
		Oe.current === e && (Ee(De), Ee(Oe)), Ae.current === e && (Ee(Ae), sh._currentValue = Se);
	}
	var Fe, Ie;
	function Le(e) {
		if (Fe === void 0) try {
			throw Error();
		} catch (e) {
			var t = e.stack.trim().match(/\n( *(at )?)/);
			Fe = t && t[1] || "", Ie = -1 < e.stack.indexOf("\n    at") ? " (<anonymous>)" : -1 < e.stack.indexOf("@") ? "@unknown:0:0" : "";
		}
		return "\n" + Fe + e + Ie;
	}
	var Re = !1;
	function ze(e, t) {
		if (!e || Re) return "";
		Re = !0;
		var n = Error.prepareStackTrace;
		Error.prepareStackTrace = void 0;
		try {
			var r = { DetermineComponentFrameRoot: function() {
				try {
					if (t) {
						var n = function() {
							throw Error();
						};
						if (Object.defineProperty(n.prototype, "props", { set: function() {
							throw Error();
						} }), typeof Reflect == "object" && Reflect.construct) {
							try {
								Reflect.construct(n, []);
							} catch (e) {
								var r = e;
							}
							Reflect.construct(e, [], n);
						} else {
							try {
								n.call();
							} catch (e) {
								r = e;
							}
							n = !1;
							try {
								var i = Object.getOwnPropertyDescriptor(e.prototype, "props");
								Object.defineProperty(e.prototype, "props", {
									configurable: !0,
									set: function() {
										throw Error();
									}
								}), n = !0, new e();
							} finally {
								n && (i === void 0 ? delete e.prototype.props : Object.defineProperty(e.prototype, "props", i));
							}
						}
					} else {
						try {
							throw Error();
						} catch (e) {
							r = e;
						}
						(n = e()) && typeof n.catch == "function" && n.catch(function() {});
					}
				} catch (e) {
					if (e && r && typeof e.stack == "string") return [e.stack, r.stack];
				}
				return [null, null];
			} };
			r.DetermineComponentFrameRoot.displayName = "DetermineComponentFrameRoot";
			var i = Object.getOwnPropertyDescriptor(r.DetermineComponentFrameRoot, "name");
			i && i.configurable && Object.defineProperty(r.DetermineComponentFrameRoot, "name", { value: "DetermineComponentFrameRoot" });
			var a = r.DetermineComponentFrameRoot(), o = a[0], s = a[1];
			if (o && s) {
				var c = o.split("\n"), l = s.split("\n");
				for (i = r = 0; r < c.length && !c[r].includes("DetermineComponentFrameRoot");) r++;
				for (; i < l.length && !l[i].includes("DetermineComponentFrameRoot");) i++;
				if (r === c.length || i === l.length) for (r = c.length - 1, i = l.length - 1; 1 <= r && 0 <= i && c[r] !== l[i];) i--;
				for (; 1 <= r && 0 <= i; r--, i--) if (c[r] !== l[i]) {
					if (r !== 1 || i !== 1) do
						if (r--, i--, 0 > i || c[r] !== l[i]) {
							var u = "\n" + c[r].replace(" at new ", " at ");
							return e.displayName && u.includes("<anonymous>") && (u = u.replace("<anonymous>", e.displayName)), u;
						}
					while (1 <= r && 0 <= i);
					break;
				}
			}
		} finally {
			Re = !1, Error.prepareStackTrace = n;
		}
		return (n = e ? e.displayName || e.name : "") ? Le(n) : "";
	}
	function Be(e, t) {
		switch (e.tag) {
			case 26:
			case 27:
			case 5: return Le(e.type);
			case 16: return Le("Lazy");
			case 13: return e.child !== t && t !== null ? Le("Suspense Fallback") : Le("Suspense");
			case 19: return Le("SuspenseList");
			case 0:
			case 15: return ze(e.type, !1);
			case 11: return ze(e.type.render, !1);
			case 1: return ze(e.type, !0);
			case 31: return Le("Activity");
			case 30: return Le("ViewTransition");
			default: return "";
		}
	}
	function Ve(e) {
		try {
			var t = "", n = null;
			do
				t += Be(e, n), n = e, e = e.return;
			while (e);
			return t;
		} catch (e) {
			return "\nError generating stack: " + e.message + "\n" + e.stack;
		}
	}
	var He = Object.prototype.hasOwnProperty, M = t.unstable_scheduleCallback, Ue = t.unstable_cancelCallback, N = t.unstable_shouldYield, We = t.unstable_requestPaint, Ge = t.unstable_now, Ke = t.unstable_getCurrentPriorityLevel, qe = t.unstable_ImmediatePriority, Je = t.unstable_UserBlockingPriority, Ye = t.unstable_NormalPriority, Xe = t.unstable_LowPriority, Ze = t.unstable_IdlePriority, Qe = t.log, $e = t.unstable_setDisableYieldValue, et = null, tt = null;
	function nt(e) {
		if (typeof Qe == "function" && $e(e), tt && typeof tt.setStrictMode == "function") try {
			tt.setStrictMode(et, e);
		} catch {}
	}
	var rt = Math.clz32 ? Math.clz32 : ot, it = Math.log, at = Math.LN2;
	function ot(e) {
		return e >>>= 0, e === 0 ? 32 : 31 - (it(e) / at | 0) | 0;
	}
	var st = 256, P = 262144, ct = 4194304;
	function lt(e) {
		var t = e & 42;
		if (t !== 0) return t;
		switch (e & -e) {
			case 1: return 1;
			case 2: return 2;
			case 4: return 4;
			case 8: return 8;
			case 16: return 16;
			case 32: return 32;
			case 64: return 64;
			case 128: return 128;
			case 256:
			case 512:
			case 1024:
			case 2048:
			case 4096:
			case 8192:
			case 16384:
			case 32768:
			case 65536:
			case 131072: return e & -e;
			case 262144:
			case 524288:
			case 1048576:
			case 2097152: return e & 3932160;
			case 4194304:
			case 8388608:
			case 16777216:
			case 33554432: return e & 62914560;
			case 67108864: return 67108864;
			case 134217728: return 134217728;
			case 268435456: return 268435456;
			case 536870912: return 536870912;
			case 1073741824: return 0;
			default: return e;
		}
	}
	function ut(e, t, n) {
		var r = e.pendingLanes;
		if (r === 0) return 0;
		var i = 0, a = e.suspendedLanes, o = e.pingedLanes;
		e = e.warmLanes;
		var s = r & 134217727;
		return s === 0 ? (s = r & ~a, s === 0 ? o === 0 ? n || (n = r & ~e, n !== 0 && (i = lt(n))) : i = lt(o) : i = lt(s)) : (r = s & ~a, r === 0 ? (o &= s, o === 0 ? n || (n = s & ~e, n !== 0 && (i = lt(n))) : i = lt(o)) : i = lt(r)), i === 0 ? 0 : t !== 0 && t !== i && (t & a) === 0 && (a = i & -i, n = t & -t, a >= n || a === 32 && n & 4194048) ? t : i;
	}
	function dt(e, t) {
		return (e.pendingLanes & ~(e.suspendedLanes & ~e.pingedLanes) & t) === 0;
	}
	function ft(e, t) {
		t & 8 && (t |= t & 32);
		var n = e.entangledLanes;
		if (n !== 0) for (e = e.entanglements, n &= t; 0 < n;) {
			var r = 31 - rt(n), i = 1 << r;
			t |= e[r], n &= ~i;
		}
		return t;
	}
	function pt(e, t) {
		switch (e) {
			case 1:
			case 2:
			case 4:
			case 8:
			case 64: return t + 250;
			case 16:
			case 32:
			case 128:
			case 256:
			case 512:
			case 1024:
			case 2048:
			case 4096:
			case 8192:
			case 16384:
			case 32768:
			case 65536:
			case 131072:
			case 262144:
			case 524288:
			case 1048576:
			case 2097152: return t + 5e3;
			case 4194304:
			case 8388608:
			case 16777216:
			case 33554432: return -1;
			case 67108864:
			case 134217728:
			case 268435456:
			case 536870912:
			case 1073741824: return -1;
			default: return -1;
		}
	}
	function mt() {
		var e = ct;
		return ct <<= 1, !(ct & 62914560) && (ct = 4194304), e;
	}
	function ht(e) {
		for (var t = [], n = 0; 31 > n; n++) t.push(e);
		return t;
	}
	function gt(e, t) {
		e.pendingLanes |= t, t !== 268435456 && (e.suspendedLanes = 0, e.pingedLanes = 0, e.warmLanes = 0);
	}
	function _t(e, t, n, r, i, a) {
		var o = e.pendingLanes;
		e.pendingLanes = n, e.suspendedLanes = 0, e.pingedLanes = 0, e.warmLanes = 0, e.expiredLanes &= n, e.entangledLanes &= n, e.errorRecoveryDisabledLanes &= n, e.shellSuspendCounter = 0;
		var s = e.entanglements, c = e.expirationTimes, l = e.hiddenUpdates;
		for (n = o & ~n; 0 < n;) {
			var u = 31 - rt(n), d = 1 << u;
			s[u] = 0, c[u] = -1;
			var f = l[u];
			if (f !== null) for (l[u] = null, u = 0; u < f.length; u++) {
				var p = f[u];
				p !== null && (p.lane &= -536870913);
			}
			n &= ~d;
		}
		r !== 0 && vt(e, r, 0), a !== 0 && i === 0 && e.tag !== 0 && (e.suspendedLanes |= a & ~(o & ~t));
	}
	function vt(e, t, n) {
		e.pendingLanes |= t, e.suspendedLanes &= ~t;
		var r = 31 - rt(t);
		e.entangledLanes |= t, e.entanglements[r] = e.entanglements[r] | 1073741824 | n & 261930;
	}
	function yt(e, t) {
		var n = e.entangledLanes |= t;
		for (e = e.entanglements; n;) {
			var r = 31 - rt(n), i = 1 << r;
			i & t | e[r] & t && (e[r] |= t), n &= ~i;
		}
	}
	function bt(e, t) {
		var n = t & -t;
		return n = n & 42 ? 1 : xt(n), (n & (e.suspendedLanes | t)) === 0 ? n : 0;
	}
	function xt(e) {
		switch (e) {
			case 2:
				e = 1;
				break;
			case 8:
				e = 4;
				break;
			case 32:
				e = 16;
				break;
			case 256:
			case 512:
			case 1024:
			case 2048:
			case 4096:
			case 8192:
			case 16384:
			case 32768:
			case 65536:
			case 131072:
			case 262144:
			case 524288:
			case 1048576:
			case 2097152:
			case 4194304:
			case 8388608:
			case 16777216:
			case 33554432:
				e = 128;
				break;
			case 268435456:
				e = 134217728;
				break;
			default: e = 0;
		}
		return e;
	}
	function St(e) {
		return e &= -e, 2 < e ? 8 < e ? e & 134217727 ? 32 : 268435456 : 8 : 2;
	}
	function Ct() {
		var e = A.p;
		return e === 0 ? (e = window.event, e === void 0 ? 32 : Ch(e.type)) : e;
	}
	function wt(e, t) {
		var n = A.p;
		try {
			return A.p = e, t();
		} finally {
			A.p = n;
		}
	}
	var Tt = Math.random().toString(36).slice(2), F = "__reactFiber$" + Tt, Et = "__reactProps$" + Tt, Dt = "__reactContainer$" + Tt, Ot = "__reactEvents$" + Tt, kt = "__reactListeners$" + Tt, At = "__reactHandles$" + Tt, jt = "__reactResources$" + Tt, Mt = "__reactMarker$" + Tt, Nt = "__reactLoad$" + Tt;
	function Pt(e) {
		delete e[F], delete e[Et], delete e[kt], delete e[At];
	}
	function Ft(e) {
		var t;
		if (t = e[F]) return t;
		for (var n = e.parentNode; n;) {
			if (t = n[Dt] || n[F]) {
				if (n = t.alternate, t.child !== null || n !== null && n.child !== null) for (e = fm(e); e !== null;) {
					if (n = e[F]) return n;
					e = fm(e);
				}
				return t;
			}
			e = n, n = e.parentNode;
		}
		return null;
	}
	function It(e) {
		if (e = e[F] || e[Dt]) {
			var t = e.tag;
			if (t === 5 || t === 6 || t === 13 || t === 31 || t === 26 || t === 27 || t === 3) return e;
		}
		return null;
	}
	function Lt(e) {
		var t = e.tag;
		if (t === 5 || t === 26 || t === 27 || t === 6) return e.stateNode;
		throw Error(s(33));
	}
	function Rt(e) {
		var t = e[jt];
		return t ||= e[jt] = {
			hoistableStyles: /* @__PURE__ */ new Map(),
			hoistableScripts: /* @__PURE__ */ new Map()
		}, t;
	}
	function zt(e) {
		e[Mt] = !0;
	}
	function Bt(e) {
		e[Nt] = void 0;
	}
	var Vt = /* @__PURE__ */ new Set(), Ht = {};
	function Ut(e, t) {
		Wt(e, t), Wt(e + "Capture", t);
	}
	function Wt(e, t) {
		for (Ht[e] = t, e = 0; e < t.length; e++) Vt.add(t[e]);
	}
	var Gt = RegExp("^[:A-Z_a-z\\u00C0-\\u00D6\\u00D8-\\u00F6\\u00F8-\\u02FF\\u0370-\\u037D\\u037F-\\u1FFF\\u200C-\\u200D\\u2070-\\u218F\\u2C00-\\u2FEF\\u3001-\\uD7FF\\uF900-\\uFDCF\\uFDF0-\\uFFFD][:A-Z_a-z\\u00C0-\\u00D6\\u00D8-\\u00F6\\u00F8-\\u02FF\\u0370-\\u037D\\u037F-\\u1FFF\\u200C-\\u200D\\u2070-\\u218F\\u2C00-\\u2FEF\\u3001-\\uD7FF\\uF900-\\uFDCF\\uFDF0-\\uFFFD\\-.0-9\\u00B7\\u0300-\\u036F\\u203F-\\u2040]*$"), Kt = {}, qt = {};
	function Jt(e) {
		return He.call(qt, e) ? !0 : He.call(Kt, e) ? !1 : Gt.test(e) ? qt[e] = !0 : (Kt[e] = !0, !1);
	}
	var I = !1;
	function Yt() {
		var e = I;
		return I = !1, e;
	}
	function Xt(e, t, n) {
		if (Jt(t)) {
			if (n === null) e.removeAttribute(t);
			else {
				switch (typeof n) {
					case "undefined":
					case "function":
					case "symbol":
						e.removeAttribute(t);
						return;
					case "boolean":
						var r = t.toLowerCase().slice(0, 5);
						if (r !== "data-" && r !== "aria-") {
							e.removeAttribute(t);
							return;
						}
				}
				e.setAttribute(t, n);
			}
		}
	}
	function Zt(e, t, n) {
		if (n === null) e.removeAttribute(t);
		else {
			switch (typeof n) {
				case "undefined":
				case "function":
				case "symbol":
				case "boolean":
					e.removeAttribute(t);
					return;
			}
			e.setAttribute(t, n);
		}
	}
	function Qt(e, t, n, r) {
		if (r === null) e.removeAttribute(n);
		else {
			switch (typeof r) {
				case "undefined":
				case "function":
				case "symbol":
				case "boolean":
					e.removeAttribute(n);
					return;
			}
			e.setAttributeNS(t, n, r);
		}
	}
	function $t(e) {
		switch (typeof e) {
			case "bigint":
			case "boolean":
			case "number":
			case "string":
			case "undefined": return e;
			case "object": return e;
			default: return "";
		}
	}
	function en(e) {
		var t = e.type;
		return (e = e.nodeName) && e.toLowerCase() === "input" && (t === "checkbox" || t === "radio");
	}
	function L(e, t, n) {
		var r = Object.getOwnPropertyDescriptor(e.constructor.prototype, t);
		if (!e.hasOwnProperty(t) && r !== void 0 && typeof r.get == "function" && typeof r.set == "function") {
			var i = r.get, a = r.set;
			return Object.defineProperty(e, t, {
				configurable: !0,
				get: function() {
					return i.call(this);
				},
				set: function(e) {
					n = "" + e, a.call(this, e);
				}
			}), Object.defineProperty(e, t, { enumerable: r.enumerable }), {
				getValue: function() {
					return n;
				},
				setValue: function(e) {
					n = "" + e;
				},
				stopTracking: function() {
					e._valueTracker = null, delete e[t];
				}
			};
		}
	}
	function tn(e) {
		if (!e._valueTracker) {
			var t = en(e) ? "checked" : "value";
			e._valueTracker = L(e, t, "" + e[t]);
		}
	}
	function nn(e) {
		if (!e) return !1;
		var t = e._valueTracker;
		if (!t) return !0;
		var n = t.getValue(), r = "";
		return e && (r = en(e) ? e.checked ? "true" : "false" : e.value), e = r, e !== n && (t.setValue(e), !0);
	}
	var R = /[\n"\\]/g;
	function rn(e) {
		return e.replace(R, function(e) {
			return "\\" + e.charCodeAt(0).toString(16) + " ";
		});
	}
	function an(e, t, n, r, i, a, o, s) {
		e.name = "", o != null && typeof o != "function" && typeof o != "symbol" && typeof o != "boolean" ? e.type = o : e.removeAttribute("type"), t == null ? o !== "submit" && o !== "reset" || e.removeAttribute("value") : o === "number" ? (t === 0 && e.value === "" || e.value != t) && (e.value = "" + $t(t)) : e.value !== "" + $t(t) && (e.value = "" + $t(t)), t == null ? n == null ? r != null && e.removeAttribute("value") : sn(e, $t(n)) : o === "number" && e.value == t ? sn(e, $t(e.value)) : sn(e, $t(t)), i == null && a != null && (e.defaultChecked = !!a), i != null && (e.checked = i && typeof i != "function" && typeof i != "symbol"), s != null && typeof s != "function" && typeof s != "symbol" && typeof s != "boolean" ? e.name = "" + $t(s) : e.removeAttribute("name");
	}
	function on(e, t, n, r, i, a, o, s) {
		if (a != null && typeof a != "function" && typeof a != "symbol" && typeof a != "boolean" && (e.type = a), t != null || n != null) {
			if (!(a !== "submit" && a !== "reset" || t != null)) {
				tn(e);
				return;
			}
			n = n == null ? "" : "" + $t(n), t = t == null ? n : "" + $t(t), s || t === e.value || (e.value = t), e.defaultValue = t;
		}
		r ??= i, r = typeof r != "function" && typeof r != "symbol" && !!r, e.checked = s ? e.checked : !!r, e.defaultChecked = !!r, o != null && typeof o != "function" && typeof o != "symbol" && typeof o != "boolean" && (e.name = o), tn(e);
	}
	function sn(e, t) {
		e.defaultValue !== "" + t && (e.defaultValue = "" + t);
	}
	function cn(e, t, n, r) {
		if (e = e.options, t) {
			t = {};
			for (var i = 0; i < n.length; i++) t["$" + n[i]] = !0;
			for (n = 0; n < e.length; n++) i = t.hasOwnProperty("$" + e[n].value), e[n].selected !== i && (e[n].selected = i), i && r && (e[n].defaultSelected = !0);
		} else {
			for (n = "" + $t(n), t = null, i = 0; i < e.length; i++) {
				if (e[i].value === n) {
					e[i].selected = !0, r && (e[i].defaultSelected = !0);
					return;
				}
				t !== null || e[i].disabled || (t = e[i]);
			}
			t !== null && (t.selected = !0);
		}
	}
	function ln(e, t, n) {
		t != null && (t = "" + $t(t), t !== e.value && (e.value = t), n == null) ? e.defaultValue !== t && (e.defaultValue = t) : e.defaultValue = n == null ? "" : "" + $t(n);
	}
	function un(e, t, n, r) {
		if (t == null) {
			if (r != null) {
				if (n != null) throw Error(s(92));
				if (xe(r)) {
					if (1 < r.length) throw Error(s(93));
					r = r[0];
				}
				n = r;
			}
			n ??= "", t = n;
		}
		n = $t(t), e.defaultValue = n, r = e.textContent, r === n && r !== "" && r !== null && (e.value = r), tn(e);
	}
	function dn(e, t) {
		if (t) {
			var n = e.firstChild;
			if (n && n === e.lastChild && n.nodeType === 3) {
				n.nodeValue = t;
				return;
			}
		}
		e.textContent = t;
	}
	var fn = new Set("animationIterationCount aspectRatio borderImageOutset borderImageSlice borderImageWidth boxFlex boxFlexGroup boxOrdinalGroup columnCount columns flex flexGrow flexPositive flexShrink flexNegative flexOrder gridArea gridRow gridRowEnd gridRowSpan gridRowStart gridColumn gridColumnEnd gridColumnSpan gridColumnStart fontWeight lineClamp lineHeight opacity order orphans scale tabSize widows zIndex zoom fillOpacity floodOpacity stopOpacity strokeDasharray strokeDashoffset strokeMiterlimit strokeOpacity strokeWidth MozAnimationIterationCount MozBoxFlex MozBoxFlexGroup MozLineClamp msAnimationIterationCount msFlex msZoom msFlexGrow msFlexNegative msFlexOrder msFlexPositive msFlexShrink msGridColumn msGridColumnSpan msGridRow msGridRowSpan WebkitAnimationIterationCount WebkitBoxFlex WebKitBoxFlexGroup WebkitBoxOrdinalGroup WebkitColumnCount WebkitColumns WebkitFlex WebkitFlexGrow WebkitFlexPositive WebkitFlexShrink WebkitLineClamp".split(" "));
	function pn(e, t, n) {
		var r = t.indexOf("--") === 0;
		n == null || typeof n == "boolean" || n === "" ? r ? e.setProperty(t, "") : t === "float" ? e.cssFloat = "" : e[t] = "" : r ? e.setProperty(t, n) : typeof n != "number" || n === 0 || fn.has(t) ? t === "float" ? e.cssFloat = n : e[t] = ("" + n).trim() : e[t] = n + "px";
	}
	function z(e, t, n) {
		if (t != null && typeof t != "object") throw Error(s(62));
		if (e = e.style, n != null) {
			for (var r in n) !n.hasOwnProperty(r) || t != null && t.hasOwnProperty(r) || (r.indexOf("--") === 0 ? e.setProperty(r, "") : r === "float" ? e.cssFloat = "" : e[r] = "", I = !0);
			for (var i in t) r = t[i], t.hasOwnProperty(i) && n[i] !== r && (pn(e, i, r), I = !0);
		} else for (var a in t) t.hasOwnProperty(a) && pn(e, a, t[a]);
	}
	function mn(e) {
		if (e.indexOf("-") === -1) return !1;
		switch (e) {
			case "annotation-xml":
			case "color-profile":
			case "font-face":
			case "font-face-src":
			case "font-face-uri":
			case "font-face-format":
			case "font-face-name":
			case "missing-glyph": return !1;
			default: return !0;
		}
	}
	var hn = /* @__PURE__ */ new Map([
		["acceptCharset", "accept-charset"],
		["htmlFor", "for"],
		["httpEquiv", "http-equiv"],
		["crossOrigin", "crossorigin"],
		["accentHeight", "accent-height"],
		["alignmentBaseline", "alignment-baseline"],
		["arabicForm", "arabic-form"],
		["baselineShift", "baseline-shift"],
		["capHeight", "cap-height"],
		["clipPath", "clip-path"],
		["clipRule", "clip-rule"],
		["colorInterpolation", "color-interpolation"],
		["colorInterpolationFilters", "color-interpolation-filters"],
		["colorProfile", "color-profile"],
		["colorRendering", "color-rendering"],
		["dominantBaseline", "dominant-baseline"],
		["enableBackground", "enable-background"],
		["fillOpacity", "fill-opacity"],
		["fillRule", "fill-rule"],
		["floodColor", "flood-color"],
		["floodOpacity", "flood-opacity"],
		["fontFamily", "font-family"],
		["fontSize", "font-size"],
		["fontSizeAdjust", "font-size-adjust"],
		["fontStretch", "font-stretch"],
		["fontStyle", "font-style"],
		["fontVariant", "font-variant"],
		["fontWeight", "font-weight"],
		["glyphName", "glyph-name"],
		["glyphOrientationHorizontal", "glyph-orientation-horizontal"],
		["glyphOrientationVertical", "glyph-orientation-vertical"],
		["horizAdvX", "horiz-adv-x"],
		["horizOriginX", "horiz-origin-x"],
		["imageRendering", "image-rendering"],
		["letterSpacing", "letter-spacing"],
		["lightingColor", "lighting-color"],
		["markerEnd", "marker-end"],
		["markerMid", "marker-mid"],
		["markerStart", "marker-start"],
		["maskType", "mask-type"],
		["overlinePosition", "overline-position"],
		["overlineThickness", "overline-thickness"],
		["paintOrder", "paint-order"],
		["panose-1", "panose-1"],
		["pointerEvents", "pointer-events"],
		["renderingIntent", "rendering-intent"],
		["shapeRendering", "shape-rendering"],
		["stopColor", "stop-color"],
		["stopOpacity", "stop-opacity"],
		["strikethroughPosition", "strikethrough-position"],
		["strikethroughThickness", "strikethrough-thickness"],
		["strokeDasharray", "stroke-dasharray"],
		["strokeDashoffset", "stroke-dashoffset"],
		["strokeLinecap", "stroke-linecap"],
		["strokeLinejoin", "stroke-linejoin"],
		["strokeMiterlimit", "stroke-miterlimit"],
		["strokeOpacity", "stroke-opacity"],
		["strokeWidth", "stroke-width"],
		["textAnchor", "text-anchor"],
		["textDecoration", "text-decoration"],
		["textRendering", "text-rendering"],
		["transformOrigin", "transform-origin"],
		["underlinePosition", "underline-position"],
		["underlineThickness", "underline-thickness"],
		["unicodeBidi", "unicode-bidi"],
		["unicodeRange", "unicode-range"],
		["unitsPerEm", "units-per-em"],
		["vAlphabetic", "v-alphabetic"],
		["vHanging", "v-hanging"],
		["vIdeographic", "v-ideographic"],
		["vMathematical", "v-mathematical"],
		["vectorEffect", "vector-effect"],
		["vertAdvY", "vert-adv-y"],
		["vertOriginX", "vert-origin-x"],
		["vertOriginY", "vert-origin-y"],
		["wordSpacing", "word-spacing"],
		["writingMode", "writing-mode"],
		["xmlnsXlink", "xmlns:xlink"],
		["xHeight", "x-height"]
	]), gn = /^[\u0000-\u001F ]*j[\r\n\t]*a[\r\n\t]*v[\r\n\t]*a[\r\n\t]*s[\r\n\t]*c[\r\n\t]*r[\r\n\t]*i[\r\n\t]*p[\r\n\t]*t[\r\n\t]*:/i;
	function _n(e) {
		return gn.test("" + e) ? "javascript:throw new Error('React has blocked a javascript: URL as a security precaution.')" : e;
	}
	function vn() {}
	var yn = null;
	function bn(e) {
		return e = e.target || e.srcElement || window, e.correspondingUseElement && (e = e.correspondingUseElement), e.nodeType === 3 ? e.parentNode : e;
	}
	var xn = null, Sn = null;
	function Cn(e) {
		var t = It(e);
		if (t && (e = t.stateNode)) {
			var n = e[Et] || null;
			a: switch (e = t.stateNode, t.type) {
				case "input":
					if (an(e, n.value, n.defaultValue, n.defaultValue, n.checked, n.defaultChecked, n.type, n.name), t = n.name, n.type === "radio" && t != null) {
						for (n = e; n.parentNode;) n = n.parentNode;
						for (n = n.querySelectorAll("input[name=\"" + rn("" + t) + "\"][type=\"radio\"]"), t = 0; t < n.length; t++) {
							var r = n[t];
							if (r !== e && r.form === e.form) {
								var i = r[Et] || null;
								if (!i) throw Error(s(90));
								an(r, i.value, i.defaultValue, i.defaultValue, i.checked, i.defaultChecked, i.type, i.name);
							}
						}
						for (t = 0; t < n.length; t++) r = n[t], r.form === e.form && nn(r);
					}
					break a;
				case "textarea":
					ln(e, n.value, n.defaultValue);
					break a;
				case "select": t = n.value, t != null && cn(e, !!n.multiple, t, !1);
			}
		}
	}
	var wn = !1;
	function Tn(e, t, n) {
		if (wn) return e(t, n);
		wn = !0;
		try {
			return e(t);
		} finally {
			if (wn = !1, (xn !== null || Sn !== null) && (zd(), xn && (t = xn, e = Sn, Sn = xn = null, Cn(t), e))) for (t = 0; t < e.length; t++) Cn(e[t]);
		}
	}
	function En(e, t) {
		var n = e.stateNode;
		if (n === null) return null;
		var r = n[Et] || null;
		if (r === null) return null;
		n = r[t];
		a: switch (t) {
			case "onClick":
			case "onClickCapture":
			case "onDoubleClick":
			case "onDoubleClickCapture":
			case "onMouseDown":
			case "onMouseDownCapture":
			case "onMouseMove":
			case "onMouseMoveCapture":
			case "onMouseUp":
			case "onMouseUpCapture":
			case "onMouseEnter":
				(r = !r.disabled) || (e = e.type, r = e !== "button" && e !== "input" && e !== "select" && e !== "textarea"), e = !r;
				break a;
			default: e = !1;
		}
		if (e) return null;
		if (n && typeof n != "function") throw Error(s(231, t, typeof n));
		return n;
	}
	var Dn = typeof window < "u" && window.document !== void 0 && window.document.createElement !== void 0, On = !1;
	if (Dn) try {
		var kn = {};
		Object.defineProperty(kn, "passive", { get: function() {
			On = !0;
		} }), window.addEventListener("test", kn, kn), window.removeEventListener("test", kn, kn);
	} catch {
		On = !1;
	}
	var An = null, jn = null, Mn = null;
	function Nn() {
		if (Mn) return Mn;
		var e, t = jn, n = t.length, r, i = "value" in An ? An.value : An.textContent, a = i.length;
		for (e = 0; e < n && t[e] === i[e]; e++);
		var o = n - e;
		for (r = 1; r <= o && t[n - r] === i[a - r]; r++);
		return Mn = i.slice(e, 1 < r ? 1 - r : void 0);
	}
	function Pn(e) {
		var t = e.keyCode;
		return "charCode" in e ? (e = e.charCode, e === 0 && t === 13 && (e = 13)) : e = t, e === 10 && (e = 13), 32 <= e || e === 13 ? e : 0;
	}
	function Fn() {
		return !0;
	}
	function In() {
		return !1;
	}
	function Ln(e) {
		function t(t, n, r, i, a) {
			for (var o in this._reactName = t, this._targetInst = r, this.type = n, this.nativeEvent = i, this.target = a, this.currentTarget = null, e) e.hasOwnProperty(o) && (t = e[o], this[o] = t ? t(i) : i[o]);
			return this.isDefaultPrevented = (i.defaultPrevented == null ? !1 === i.returnValue : i.defaultPrevented) ? Fn : In, this.isPropagationStopped = In, this;
		}
		return T(t.prototype, {
			preventDefault: function() {
				this.defaultPrevented = !0;
				var e = this.nativeEvent;
				e && (e.preventDefault ? e.preventDefault() : typeof e.returnValue != "unknown" && (e.returnValue = !1), this.isDefaultPrevented = Fn);
			},
			stopPropagation: function() {
				var e = this.nativeEvent;
				e && (e.stopPropagation ? e.stopPropagation() : typeof e.cancelBubble != "unknown" && (e.cancelBubble = !0), this.isPropagationStopped = Fn);
			},
			persist: function() {},
			isPersistent: Fn
		}), t;
	}
	var Rn = {
		eventPhase: 0,
		bubbles: 0,
		cancelable: 0,
		timeStamp: function(e) {
			return e.timeStamp || Date.now();
		},
		defaultPrevented: 0,
		isTrusted: 0
	}, zn = Ln(Rn), Bn = T({}, Rn, {
		view: 0,
		detail: 0
	}), Vn = Ln(Bn), Hn, Un, Wn, Gn = T({}, Bn, {
		screenX: 0,
		screenY: 0,
		clientX: 0,
		clientY: 0,
		pageX: 0,
		pageY: 0,
		ctrlKey: 0,
		shiftKey: 0,
		altKey: 0,
		metaKey: 0,
		getModifierState: nr,
		button: 0,
		buttons: 0,
		relatedTarget: function(e) {
			return e.relatedTarget === void 0 ? e.fromElement === e.srcElement ? e.toElement : e.fromElement : e.relatedTarget;
		},
		movementX: function(e) {
			return "movementX" in e ? e.movementX : (e !== Wn && (Wn && e.type === "mousemove" ? (Hn = e.screenX - Wn.screenX, Un = e.screenY - Wn.screenY) : Un = Hn = 0, Wn = e), Hn);
		},
		movementY: function(e) {
			return "movementY" in e ? e.movementY : Un;
		}
	}), Kn = Ln(Gn), qn = Ln(T({}, Gn, { dataTransfer: 0 })), Jn = Ln(T({}, Bn, { relatedTarget: 0 })), Yn = Ln(T({}, Rn, {
		animationName: 0,
		elapsedTime: 0,
		pseudoElement: 0
	})), Xn = Ln(T({}, Rn, { clipboardData: function(e) {
		return "clipboardData" in e ? e.clipboardData : window.clipboardData;
	} })), Zn = Ln(T({}, Rn, { data: 0 })), Qn = {
		Esc: "Escape",
		Spacebar: " ",
		Left: "ArrowLeft",
		Up: "ArrowUp",
		Right: "ArrowRight",
		Down: "ArrowDown",
		Del: "Delete",
		Win: "OS",
		Menu: "ContextMenu",
		Apps: "ContextMenu",
		Scroll: "ScrollLock",
		MozPrintableKey: "Unidentified"
	}, $n = {
		8: "Backspace",
		9: "Tab",
		12: "Clear",
		13: "Enter",
		16: "Shift",
		17: "Control",
		18: "Alt",
		19: "Pause",
		20: "CapsLock",
		27: "Escape",
		32: " ",
		33: "PageUp",
		34: "PageDown",
		35: "End",
		36: "Home",
		37: "ArrowLeft",
		38: "ArrowUp",
		39: "ArrowRight",
		40: "ArrowDown",
		45: "Insert",
		46: "Delete",
		112: "F1",
		113: "F2",
		114: "F3",
		115: "F4",
		116: "F5",
		117: "F6",
		118: "F7",
		119: "F8",
		120: "F9",
		121: "F10",
		122: "F11",
		123: "F12",
		144: "NumLock",
		145: "ScrollLock",
		224: "Meta"
	}, er = {
		Alt: "altKey",
		Control: "ctrlKey",
		Meta: "metaKey",
		Shift: "shiftKey"
	};
	function tr(e) {
		var t = this.nativeEvent;
		return t.getModifierState ? t.getModifierState(e) : (e = er[e]) ? !!t[e] : !1;
	}
	function nr() {
		return tr;
	}
	var rr = Ln(T({}, Bn, {
		key: function(e) {
			if (e.key) {
				var t = Qn[e.key] || e.key;
				if (t !== "Unidentified") return t;
			}
			return e.type === "keypress" ? (e = Pn(e), e === 13 ? "Enter" : String.fromCharCode(e)) : e.type === "keydown" || e.type === "keyup" ? $n[e.keyCode] || "Unidentified" : "";
		},
		code: 0,
		location: 0,
		ctrlKey: 0,
		shiftKey: 0,
		altKey: 0,
		metaKey: 0,
		repeat: 0,
		locale: 0,
		getModifierState: nr,
		charCode: function(e) {
			return e.type === "keypress" ? Pn(e) : 0;
		},
		keyCode: function(e) {
			return e.type === "keydown" || e.type === "keyup" ? e.keyCode : 0;
		},
		which: function(e) {
			return e.type === "keypress" ? Pn(e) : e.type === "keydown" || e.type === "keyup" ? e.keyCode : 0;
		}
	})), ir = Ln(T({}, Gn, {
		pointerId: 0,
		width: 0,
		height: 0,
		pressure: 0,
		tangentialPressure: 0,
		tiltX: 0,
		tiltY: 0,
		twist: 0,
		pointerType: 0,
		isPrimary: 0
	})), ar = Ln(T({}, Rn, { submitter: 0 })), or = Ln(T({}, Bn, {
		touches: 0,
		targetTouches: 0,
		changedTouches: 0,
		altKey: 0,
		metaKey: 0,
		ctrlKey: 0,
		shiftKey: 0,
		getModifierState: nr
	})), sr = Ln(T({}, Rn, {
		propertyName: 0,
		elapsedTime: 0,
		pseudoElement: 0
	})), cr = Ln(T({}, Gn, {
		deltaX: function(e) {
			return "deltaX" in e ? e.deltaX : "wheelDeltaX" in e ? -e.wheelDeltaX : 0;
		},
		deltaY: function(e) {
			return "deltaY" in e ? e.deltaY : "wheelDeltaY" in e ? -e.wheelDeltaY : "wheelDelta" in e ? -e.wheelDelta : 0;
		},
		deltaZ: 0,
		deltaMode: 0
	})), lr = Ln(T({}, Rn, {
		newState: 0,
		oldState: 0,
		source: 0
	})), ur = [
		9,
		13,
		27,
		32
	], dr = Dn && "CompositionEvent" in window, fr = null;
	Dn && "documentMode" in document && (fr = document.documentMode);
	var pr = Dn && "TextEvent" in window && !fr, mr = Dn && (!dr || fr && 8 < fr && 11 >= fr), hr = " ", gr = !1;
	function _r(e, t) {
		switch (e) {
			case "keyup": return ur.indexOf(t.keyCode) !== -1;
			case "keydown": return t.keyCode !== 229;
			case "keypress":
			case "mousedown":
			case "focusout": return !0;
			default: return !1;
		}
	}
	function vr(e) {
		return e = e.detail, typeof e == "object" && "data" in e ? e.data : null;
	}
	var yr = !1;
	function br(e, t) {
		switch (e) {
			case "compositionend": return vr(t);
			case "keypress": return t.which === 32 ? (gr = !0, hr) : null;
			case "textInput": return e = t.data, e === hr && gr ? null : e;
			default: return null;
		}
	}
	function xr(e, t) {
		if (yr) return e === "compositionend" || !dr && _r(e, t) ? (e = Nn(), Mn = jn = An = null, yr = !1, e) : null;
		switch (e) {
			case "paste": return null;
			case "keypress":
				if (!(t.ctrlKey || t.altKey || t.metaKey) || t.ctrlKey && t.altKey) {
					if (t.char && 1 < t.char.length) return t.char;
					if (t.which) return String.fromCharCode(t.which);
				}
				return null;
			case "compositionend": return mr && t.locale !== "ko" ? null : t.data;
			default: return null;
		}
	}
	var Sr = {
		color: !0,
		date: !0,
		datetime: !0,
		"datetime-local": !0,
		email: !0,
		month: !0,
		number: !0,
		password: !0,
		range: !0,
		search: !0,
		tel: !0,
		text: !0,
		time: !0,
		url: !0,
		week: !0
	};
	function Cr(e) {
		var t = e && e.nodeName && e.nodeName.toLowerCase();
		return t === "input" ? !!Sr[e.type] : t === "textarea";
	}
	function wr(e, t, n, r) {
		xn ? Sn ? Sn.push(r) : Sn = [r] : xn = r, t = Jf(t, "onChange"), 0 < t.length && (n = new zn("onChange", "change", null, n, r), e.push({
			event: n,
			listeners: t
		}));
	}
	var Tr = null, Er = null;
	function Dr(e) {
		Vf(e, 0);
	}
	function Or(e) {
		if (nn(Lt(e))) return e;
	}
	function kr(e, t) {
		if (e === "change") return t;
	}
	var Ar = !1;
	if (Dn) {
		var jr;
		if (Dn) {
			var Mr = "oninput" in document;
			if (!Mr) {
				var Nr = document.createElement("div");
				Nr.setAttribute("oninput", "return;"), Mr = typeof Nr.oninput == "function";
			}
			jr = Mr;
		} else jr = !1;
		Ar = jr && (!document.documentMode || 9 < document.documentMode);
	}
	function Pr() {
		Tr && (Tr.detachEvent("onpropertychange", Fr), Er = Tr = null);
	}
	function Fr(e) {
		if (e.propertyName === "value" && Or(Er)) {
			var t = [];
			wr(t, Er, e, bn(e)), Tn(Dr, t);
		}
	}
	function Ir(e, t, n) {
		e === "focusin" ? (Pr(), Tr = t, Er = n, Tr.attachEvent("onpropertychange", Fr)) : e === "focusout" && Pr();
	}
	function Lr(e) {
		if (e === "selectionchange" || e === "keyup" || e === "keydown") return Or(Er);
	}
	function Rr(e, t) {
		if (e === "click") return Or(t);
	}
	function zr(e, t) {
		if (e === "input" || e === "change") return Or(t);
	}
	function Br(e, t) {
		return e === t && (e !== 0 || 1 / e == 1 / t) || e !== e && t !== t;
	}
	var Vr = typeof Object.is == "function" ? Object.is : Br;
	function Hr(e, t) {
		if (Vr(e, t)) return !0;
		if (typeof e != "object" || !e || typeof t != "object" || !t) return !1;
		var n = Object.keys(e), r = Object.keys(t);
		if (n.length !== r.length) return !1;
		for (r = 0; r < n.length; r++) {
			var i = n[r];
			if (!He.call(t, i) || !Vr(e[i], t[i])) return !1;
		}
		return !0;
	}
	function Ur(e) {
		if (e ||= typeof document < "u" ? document : void 0, e === void 0) return null;
		try {
			return e.activeElement || e.body;
		} catch {
			return e.body;
		}
	}
	function Wr(e) {
		for (; e && e.firstChild;) e = e.firstChild;
		return e;
	}
	function Gr(e, t) {
		var n = Wr(e);
		e = 0;
		for (var r; n;) {
			if (n.nodeType === 3) {
				if (r = e + n.textContent.length, e <= t && r >= t) return {
					node: n,
					offset: t - e
				};
				e = r;
			}
			a: {
				for (; n;) {
					if (n.nextSibling) {
						n = n.nextSibling;
						break a;
					}
					n = n.parentNode;
				}
				n = void 0;
			}
			n = Wr(n);
		}
	}
	function Kr(e, t) {
		return e && t ? e === t ? !0 : e && e.nodeType === 3 ? !1 : t && t.nodeType === 3 ? Kr(e, t.parentNode) : "contains" in e ? e.contains(t) : e.compareDocumentPosition ? !!(e.compareDocumentPosition(t) & 16) : !1 : !1;
	}
	function qr(e) {
		e = e != null && e.ownerDocument != null && e.ownerDocument.defaultView != null ? e.ownerDocument.defaultView : window;
		for (var t = Ur(e.document); t instanceof e.HTMLIFrameElement;) {
			try {
				var n = typeof t.contentWindow.location.href == "string";
			} catch {
				n = !1;
			}
			if (n) e = t.contentWindow;
			else break;
			t = Ur(e.document);
		}
		return t;
	}
	function Jr(e) {
		var t = e && e.nodeName && e.nodeName.toLowerCase();
		return t && (t === "input" && (e.type === "text" || e.type === "search" || e.type === "tel" || e.type === "url" || e.type === "password") || t === "textarea" || e.contentEditable === "true");
	}
	var Yr = Dn && "documentMode" in document && 11 >= document.documentMode, Xr = null, Zr = null, Qr = null, $r = !1;
	function ei(e, t, n) {
		var r = n.window === n ? n.document : n.nodeType === 9 ? n : n.ownerDocument;
		$r || Xr == null || Xr !== Ur(r) || (r = Xr, "selectionStart" in r && Jr(r) ? r = {
			start: r.selectionStart,
			end: r.selectionEnd
		} : (r = (r.ownerDocument && r.ownerDocument.defaultView || window).getSelection(), r = {
			anchorNode: r.anchorNode,
			anchorOffset: r.anchorOffset,
			focusNode: r.focusNode,
			focusOffset: r.focusOffset
		}), Qr && Hr(Qr, r) || (Qr = r, r = Jf(Zr, "onSelect"), 0 < r.length && (t = new zn("onSelect", "select", null, t, n), e.push({
			event: t,
			listeners: r
		}), t.target = Xr)));
	}
	function ti(e, t) {
		var n = {};
		return n[e.toLowerCase()] = t.toLowerCase(), n["Webkit" + e] = "webkit" + t, n["Moz" + e] = "moz" + t, n;
	}
	var ni = {
		animationend: ti("Animation", "AnimationEnd"),
		animationiteration: ti("Animation", "AnimationIteration"),
		animationstart: ti("Animation", "AnimationStart"),
		transitionrun: ti("Transition", "TransitionRun"),
		transitionstart: ti("Transition", "TransitionStart"),
		transitioncancel: ti("Transition", "TransitionCancel"),
		transitionend: ti("Transition", "TransitionEnd")
	}, ri = {}, ii = {};
	Dn && (ii = document.createElement("div").style, "AnimationEvent" in window || (delete ni.animationend.animation, delete ni.animationiteration.animation, delete ni.animationstart.animation), "TransitionEvent" in window || delete ni.transitionend.transition);
	function ai(e) {
		if (ri[e]) return ri[e];
		if (!ni[e]) return e;
		var t = ni[e], n;
		for (n in t) if (t.hasOwnProperty(n) && n in ii) return ri[e] = t[n];
		return e;
	}
	var oi = ai("animationend"), si = ai("animationiteration"), ci = ai("animationstart"), li = ai("transitionrun"), ui = ai("transitionstart"), di = ai("transitioncancel"), fi = ai("transitionend"), pi = /* @__PURE__ */ new Map(), mi = "abort auxClick beforeToggle cancel canPlay canPlayThrough click close contextMenu copy cut drag dragEnd dragEnter dragExit dragLeave dragOver dragStart drop durationChange emptied encrypted ended error fullscreenChange fullscreenError gotPointerCapture input invalid keyDown keyPress keyUp load loadedData loadedMetadata loadStart lostPointerCapture mouseDown mouseMove mouseOut mouseOver mouseUp paste pause play playing pointerCancel pointerDown pointerMove pointerOut pointerOver pointerUp progress rateChange reset resize seeked seeking stalled submit suspend timeUpdate touchCancel touchEnd touchStart volumeChange scroll toggle touchMove waiting wheel".split(" ");
	mi.push("scrollEnd");
	function hi(e, t) {
		pi.set(e, t), Ut(t, [e]);
	}
	var gi = 0;
	function _i(e, t) {
		if (e.name != null && e.name !== "auto") return e.name;
		if (t.autoName !== null) return t.autoName;
		e = bd.identifierPrefix;
		var n = gi++;
		return e = "_" + e + "t_" + n.toString(32) + "_", t.autoName = e;
	}
	function vi(e) {
		if (e == null || typeof e == "string") return e;
		var t = null, n = Od;
		if (n !== null) for (var r = 0; r < n.length; r++) {
			var i = e[n[r]];
			if (i != null) {
				if (i === "none") return "none";
				t = t == null ? i : t + (" " + i);
			}
		}
		return t ?? e.default;
	}
	function yi(e, t) {
		return e = vi(e), t = vi(t), t == null ? e === "auto" ? null : e : t === "auto" ? null : t;
	}
	var bi = typeof reportError == "function" ? reportError : function(e) {
		if (typeof window == "object" && typeof window.ErrorEvent == "function") {
			var t = new window.ErrorEvent("error", {
				bubbles: !0,
				cancelable: !0,
				message: typeof e == "object" && e && typeof e.message == "string" ? String(e.message) : String(e),
				error: e
			});
			if (!window.dispatchEvent(t)) return;
		} else if (typeof process == "object" && typeof process.emit == "function") {
			process.emit("uncaughtException", e);
			return;
		}
		console.error(e);
	}, xi = [], Si = 0, Ci = 0;
	function wi() {
		for (var e = Si, t = Ci = Si = 0; t < e;) {
			var n = xi[t];
			xi[t++] = null;
			var r = xi[t];
			xi[t++] = null;
			var i = xi[t];
			xi[t++] = null;
			var a = xi[t];
			if (xi[t++] = null, r !== null && i !== null) {
				var o = r.pending;
				o === null ? i.next = i : (i.next = o.next, o.next = i), r.pending = i;
			}
			a !== 0 && Oi(n, i, a);
		}
	}
	function Ti(e, t, n, r) {
		xi[Si++] = e, xi[Si++] = t, xi[Si++] = n, xi[Si++] = r, Ci |= r, e.lanes |= r, e = e.alternate, e !== null && (e.lanes |= r);
	}
	function Ei(e, t, n, r) {
		return Ti(e, t, n, r), ki(e);
	}
	function Di(e, t) {
		return Ti(e, null, null, t), ki(e);
	}
	function Oi(e, t, n) {
		e.lanes |= n;
		var r = e.alternate;
		r !== null && (r.lanes |= n);
		for (var i = !1, a = e.return; a !== null;) a.childLanes |= n, r = a.alternate, r !== null && (r.childLanes |= n), a.tag === 22 && (e = a.stateNode, e === null || e._visibility & 1 || (i = !0)), e = a, a = a.return;
		return e.tag === 3 ? (a = e.stateNode, i && t !== null && (i = 31 - rt(n), e = a.hiddenUpdates, r = e[i], r === null ? e[i] = [t] : r.push(t), t.lane = n | 536870912), a) : null;
	}
	function ki(e) {
		if (50 < kd) throw kd = 0, Ad = null, Error(s(185));
		for (var t = e.return; t !== null;) e = t, t = e.return;
		return e.tag === 3 ? e.stateNode : null;
	}
	var Ai = {};
	function ji(e, t, n, r) {
		this.tag = e, this.key = n, this.sibling = this.child = this.return = this.stateNode = this.type = this.elementType = null, this.index = 0, this.refCleanup = this.ref = null, this.pendingProps = t, this.dependencies = this.memoizedState = this.updateQueue = this.memoizedProps = null, this.mode = r, this.subtreeFlags = this.flags = 0, this.deletions = null, this.childLanes = this.lanes = 0, this.alternate = null;
	}
	function Mi(e, t, n, r) {
		return new ji(e, t, n, r);
	}
	function Ni(e) {
		return e = e.prototype, !(!e || !e.isReactComponent);
	}
	function Pi(e, t) {
		var n = e.alternate;
		return n === null ? (n = Mi(e.tag, t, e.key, e.mode), n.elementType = e.elementType, n.type = e.type, n.stateNode = e.stateNode, n.alternate = e, e.alternate = n) : (n.pendingProps = t, n.type = e.type, n.flags = 0, n.subtreeFlags = 0, n.deletions = null), n.flags = e.flags & 1206910976, n.childLanes = e.childLanes, n.lanes = e.lanes, n.child = e.child, n.memoizedProps = e.memoizedProps, n.memoizedState = e.memoizedState, n.updateQueue = e.updateQueue, t = e.dependencies, n.dependencies = t === null ? null : {
			lanes: t.lanes,
			firstContext: t.firstContext
		}, n.sibling = e.sibling, n.index = e.index, n.ref = e.ref, n.refCleanup = e.refCleanup, n;
	}
	function Fi(e, t) {
		e.flags &= 1206910978;
		var n = e.alternate;
		return n === null ? (e.childLanes = 0, e.lanes = t, e.child = null, e.subtreeFlags = 0, e.memoizedProps = null, e.memoizedState = null, e.updateQueue = null, e.dependencies = null, e.stateNode = null) : (e.childLanes = n.childLanes, e.lanes = n.lanes, e.child = n.child, e.subtreeFlags = 0, e.deletions = null, e.memoizedProps = n.memoizedProps, e.memoizedState = n.memoizedState, e.updateQueue = n.updateQueue, e.type = n.type, t = n.dependencies, e.dependencies = t === null ? null : {
			lanes: t.lanes,
			firstContext: t.firstContext
		}), e;
	}
	function Ii(e, t, n, r, i, a) {
		var o = 0;
		if (r = e, typeof r == "function") Ni(r) && (o = 1);
		else if (typeof r == "string") o = qm(e, n, De.current) ? 26 : e === "html" || e === "head" || e === "body" ? 27 : 5;
		else a: switch (r) {
			case fe: return e = Mi(31, n, t, i), e.elementType = fe, e.lanes = a, e;
			case E: return Li(n.children, i, a, t);
			case ae:
				o = 8, i |= 24;
				break;
			case oe: return e = Mi(12, n, t, i | 2), e.elementType = oe, e.lanes = a, e;
			case le: return e = Mi(13, n, t, i), e.elementType = le, e.lanes = a, e;
			case O: return e = Mi(19, n, t, i), e.elementType = O, e.lanes = a, e;
			case pe:
			case he: return e = i | 32, e = Mi(30, n, t, e), e.elementType = he, e.lanes = a, e.stateNode = {
				autoName: null,
				paired: null,
				clones: null,
				ref: null
			}, e;
			default:
				if (typeof r == "object" && r) switch (r.$$typeof) {
					case D:
						o = 10;
						break a;
					case se:
						o = 9;
						break a;
					case ce:
						o = 11;
						break a;
					case ue:
						o = 14;
						break a;
					case de:
						o = 16, r = null;
						break a;
				}
				o = 29, n = Error(s(130, e === null ? "null" : typeof e, "")), r = null;
		}
		return t = Mi(o, n, t, i), t.elementType = e, t.type = r, t.lanes = a, t;
	}
	function Li(e, t, n, r) {
		return e = Mi(7, e, r, t), e.lanes = n, e;
	}
	function Ri(e, t, n) {
		return e = Mi(6, e, null, t), e.lanes = n, e;
	}
	function zi(e) {
		var t = Mi(18, null, null, 0);
		return t.stateNode = e, t;
	}
	function Bi(e, t, n) {
		return t = Mi(4, e.children === null ? [] : e.children, e.key, t), t.lanes = n, t.stateNode = {
			containerInfo: e.containerInfo,
			pendingChildren: null,
			implementation: e.implementation
		}, t;
	}
	var Vi = /* @__PURE__ */ new WeakMap();
	function Hi(e, t) {
		if (typeof e == "object" && e) {
			var n = Vi.get(e);
			return n === void 0 ? (t = {
				value: e,
				source: t,
				stack: Ve(t)
			}, Vi.set(e, t), t) : n;
		}
		return {
			value: e,
			source: t,
			stack: Ve(t)
		};
	}
	var Ui = [], Wi = 0, Gi = null, Ki = 0, qi = [], Ji = 0, Yi = null, Xi = 1, Zi = "";
	function Qi(e, t) {
		Ui[Wi++] = Ki, Ui[Wi++] = Gi, Gi = e, Ki = t;
	}
	function $i(e, t, n) {
		qi[Ji++] = Xi, qi[Ji++] = Zi, qi[Ji++] = Yi, Yi = e;
		var r = Xi;
		e = Zi;
		var i = 32 - rt(r) - 1;
		r &= ~(1 << i), n += 1;
		var a = 32 - rt(t) + i;
		if (30 < a) {
			var o = i - i % 5;
			a = (r & (1 << o) - 1).toString(32), r >>= o, i -= o, Xi = 1 << 32 - rt(t) + i | n << i | r, Zi = a + e;
		} else Xi = 1 << a | n << i | r, Zi = e;
	}
	function ea(e) {
		e.return !== null && (Qi(e, 1), $i(e, 1, 0));
	}
	function ta(e) {
		for (; e === Gi;) Gi = Ui[--Wi], Ui[Wi] = null, Ki = Ui[--Wi], Ui[Wi] = null;
		for (; e === Yi;) Yi = qi[--Ji], qi[Ji] = null, Zi = qi[--Ji], qi[Ji] = null, Xi = qi[--Ji], qi[Ji] = null;
	}
	function na(e, t) {
		qi[Ji++] = Xi, qi[Ji++] = Zi, qi[Ji++] = Yi, Xi = t.id, Zi = t.overflow, Yi = e;
	}
	var ra = null, B = null, V = !1, ia = null, aa = !1, oa = Error(s(519));
	function sa(e) {
		throw pa(Hi(Error(s(418, 1 < arguments.length && arguments[1] !== void 0 && arguments[1] ? "text" : "HTML", "")), e)), oa;
	}
	function ca(e) {
		var t = e.stateNode, n = e.type, r = e.memoizedProps;
		switch (t[F] = e, t[Et] = r, n) {
			case "dialog":
				Q("cancel", t), Q("close", t);
				break;
			case "iframe":
			case "object":
			case "embed":
				Q("load", t);
				break;
			case "video":
			case "audio":
				for (n = 0; n < zf.length; n++) Q(zf[n], t);
				break;
			case "source":
				Q("error", t);
				break;
			case "img":
			case "image":
			case "link":
				Q("error", t), Q("load", t);
				break;
			case "details":
				Q("toggle", t);
				break;
			case "input":
				Q("invalid", t), on(t, r.value, r.defaultValue, r.checked, r.defaultChecked, r.type, r.name, !0);
				break;
			case "select":
				Q("invalid", t);
				break;
			case "textarea": Q("invalid", t), un(t, r.value, r.defaultValue, r.children);
		}
		n = r.children, typeof n != "string" && typeof n != "number" && typeof n != "bigint" || t.textContent === "" + n || !0 === r.suppressHydrationWarning || ep(t.textContent, n) ? (r.popover != null && (Q("beforetoggle", t), Q("toggle", t)), r.onScroll != null && Q("scroll", t), r.onScrollEnd != null && Q("scrollend", t), r.onClick != null && (t.onclick = vn), t = !0) : t = !1, t || sa(e, !0);
	}
	function la(e) {
		for (ra = e.return; ra;) switch (ra.tag) {
			case 5:
			case 31:
			case 13:
				aa = !1;
				return;
			case 27:
			case 3:
				aa = !0;
				return;
			default: ra = ra.return;
		}
	}
	function ua(e) {
		if (e !== ra) return !1;
		if (!V) return la(e), V = !0, !1;
		var t = e.tag, n;
		if ((n = t !== 3 && t !== 27) && ((n = t === 5) && (n = e.type, n = n === "form" || n === "button" || pp(e.type, e.memoizedProps)), n = !n), n && B && sa(e), la(e), t === 13) {
			if (e = e.memoizedState, e = e === null ? null : e.dehydrated, !e) throw Error(s(317));
			B = dm(e);
		} else if (t === 31) {
			if (e = e.memoizedState, e = e === null ? null : e.dehydrated, !e) throw Error(s(317));
			B = dm(e);
		} else t === 27 ? (t = B, Sp(e.type) ? (e = um, um = null, B = e) : B = t) : B = ra ? lm(e.stateNode.nextSibling) : null;
		return !0;
	}
	function da() {
		B = ra = null, V = !1;
	}
	function fa() {
		var e = ia;
		return e !== null && (fd === null ? fd = e : fd.push.apply(fd, e), ia = null), e;
	}
	function pa(e) {
		ia === null ? ia = [e] : ia.push(e);
	}
	var ma = Te(null), ha = null, ga = null;
	function _a(e, t, n) {
		j(ma, t._currentValue), t._currentValue = n;
	}
	function va(e) {
		e._currentValue = ma.current, Ee(ma);
	}
	function ya(e, t, n) {
		for (; e !== null;) {
			var r = e.alternate;
			if ((e.childLanes & t) === t ? r !== null && (r.childLanes & t) !== t && (r.childLanes |= t) : (e.childLanes |= t, r !== null && (r.childLanes |= t)), e === n) break;
			e = e.return;
		}
	}
	function ba(e, t, n, r) {
		var i = e.child;
		for (i !== null && (i.return = e); i !== null;) {
			var a = i.dependencies;
			if (a !== null) {
				var o = i.child;
				a = a.firstContext;
				a: for (; a !== null;) {
					var c = a;
					a = i;
					for (var l = 0; l < t.length; l++) if (c.context === t[l]) {
						a.lanes |= n, c = a.alternate, c !== null && (c.lanes |= n), ya(a.return, n, e), r || (o = null);
						break a;
					}
					a = c.next;
				}
			} else if (i.tag === 18) {
				if (o = i.return, o === null) throw Error(s(341));
				o.lanes |= n, a = o.alternate, a !== null && (a.lanes |= n), ya(o, n, e), o = null;
			} else i.tag === 13 && i.memoizedState !== null && i.memoizedState.dehydrated === null ? (i.lanes |= n, o = i.alternate, o !== null && (o.lanes |= n), ya(i.return, n, e), o = i.child, o = o === null ? null : o.sibling) : o = i.child;
			if (o !== null) o.return = i;
			else for (o = i; o !== null;) {
				if (o === e) {
					o = null;
					break;
				}
				if (i = o.sibling, i !== null) {
					i.return = o.return, o = i;
					break;
				}
				o = o.return;
			}
			i = o;
		}
	}
	function xa(e, t, n, r) {
		e = null;
		for (var i = t, a = !1; i !== null;) {
			if (!a) {
				if (i.flags & 524288) a = !0;
				else if (i.flags & 262144) break;
			}
			if (i.tag === 10) {
				var o = i.alternate;
				if (o === null) throw Error(s(387));
				if (o = o.memoizedProps, o !== null) {
					var c = i.type;
					Vr(i.pendingProps.value, o.value) || (e === null ? e = [c] : e.push(c));
				}
			} else if (i === Ae.current) {
				if (o = i.alternate, o === null) throw Error(s(387));
				o.memoizedState.memoizedState !== i.memoizedState.memoizedState && (e === null ? e = [sh] : e.push(sh));
			}
			i = i.return;
		}
		return e !== null && ba(t, e, n, r), t.flags |= 262144, e !== null;
	}
	function Sa(e) {
		for (e = e.firstContext; e !== null;) {
			if (!Vr(e.context._currentValue, e.memoizedValue)) return !0;
			e = e.next;
		}
		return !1;
	}
	function Ca(e) {
		ha = e, ga = null, e = e.dependencies, e !== null && (e.firstContext = null);
	}
	function wa(e) {
		return Ea(ha, e);
	}
	function Ta(e, t) {
		return ha === null && Ca(e), Ea(e, t);
	}
	function Ea(e, t) {
		var n = t._currentValue;
		if (t = {
			context: t,
			memoizedValue: n,
			next: null
		}, ga === null) {
			if (e === null) throw Error(s(308));
			ga = t, e.dependencies = {
				lanes: 0,
				firstContext: t
			}, e.flags |= 524288;
		} else ga = ga.next = t;
		return n;
	}
	var Da = typeof AbortController < "u" ? AbortController : function() {
		var e = [], t = this.signal = {
			aborted: !1,
			addEventListener: function(t, n) {
				e.push(n);
			}
		};
		this.abort = function() {
			t.aborted = !0, e.forEach(function(e) {
				return e();
			});
		};
	}, Oa = t.unstable_scheduleCallback, ka = t.unstable_NormalPriority, Aa = {
		$$typeof: D,
		Consumer: null,
		Provider: null,
		_currentValue: null,
		_currentValue2: null,
		_threadCount: 0
	};
	function ja() {
		return {
			controller: new Da(),
			data: /* @__PURE__ */ new Map(),
			refCount: 0
		};
	}
	function Ma(e) {
		e.refCount--, e.refCount === 0 && Oa(ka, function() {
			e.controller.abort();
		});
	}
	function Na(e, t) {
		if (e.pendingLanes & 4194048) {
			var n = e.transitionTypes;
			for (n === null && (n = e.transitionTypes = []), e = 0; e < t.length; e++) {
				var r = t[e];
				n.indexOf(r) === -1 && n.push(r);
			}
		}
	}
	var Pa = null;
	function Fa(e) {
		var t = e.transitionTypes;
		return e.transitionTypes = null, t;
	}
	var Ia = null, La = 0, Ra = 0, za = null;
	function Ba(e, t) {
		if (Ia === null) {
			var n = Ia = [];
			La = 0, Ra = Pf(), za = {
				status: "pending",
				value: void 0,
				then: function(e) {
					n.push(e);
				}
			};
		}
		return La++, t.then(Va, Va), t;
	}
	function Va() {
		if (--La === 0 && (Pa = null, Ia !== null)) {
			za !== null && (za.status = "fulfilled");
			var e = Ia;
			Ia = null, Ra = 0, za = null;
			for (var t = 0; t < e.length; t++) (0, e[t])();
		}
	}
	function Ha(e, t) {
		var n = [], r = {
			status: "pending",
			value: null,
			reason: null,
			then: function(e) {
				n.push(e);
			}
		};
		return e.then(function() {
			r.status = "fulfilled", r.value = t;
			for (var e = 0; e < n.length; e++) (0, n[e])(t);
		}, function(e) {
			for (r.status = "rejected", r.reason = e, e = 0; e < n.length; e++) (0, n[e])(void 0);
		}), r;
	}
	var Ua = k.S;
	k.S = function(e, t) {
		if (hd = Ge(), typeof t == "object" && t && typeof t.then == "function" && Ba(e, t), Pa !== null) for (var n = bf; n !== null;) Na(n, Pa), n = n.next;
		if (n = e.types, n !== null) {
			for (var r = bf; r !== null;) Na(r, n), r = r.next;
			if (Ra !== 0) {
				r = Pa, r === null && (r = Pa = []);
				for (var i = 0; i < n.length; i++) {
					var a = n[i];
					r.indexOf(a) === -1 && r.push(a);
				}
			}
		}
		Ua !== null && Ua(e, t);
	};
	var Wa = Te(null);
	function Ga() {
		var e = Wa.current;
		return e === null ? q.pooledCache : e;
	}
	function Ka(e, t) {
		t === null ? j(Wa, Wa.current) : j(Wa, t.pool);
	}
	function qa() {
		var e = Ga();
		return e === null ? null : {
			parent: Aa._currentValue,
			pool: e
		};
	}
	var Ja = Error(s(460)), Ya = Error(s(474)), Xa = Error(s(542)), Za = { then: function() {} };
	function Qa(e) {
		return e = e.status, e === "fulfilled" || e === "rejected";
	}
	function $a(e, t, n) {
		switch (n = e[n], n === void 0 ? e.push(t) : n !== t && (t.then(vn, vn), t = n), t.status) {
			case "fulfilled": return t.value;
			case "rejected": throw e = t.reason, ro(e), e === void 0 && !("reason" in t) ? Error(s(600)) : e;
			default:
				if (typeof t.status == "string") t.then(vn, vn);
				else {
					if (e = q, e !== null && 100 < e.shellSuspendCounter) throw Error(s(482));
					e = t, e.status = "pending", e.then(function(e) {
						if (t.status === "pending") {
							var n = t;
							n.status = "fulfilled", n.value = e;
						}
					}, function(e) {
						if (t.status === "pending") {
							var n = t;
							n.status = "rejected", n.reason = e;
						}
					});
				}
				switch (t.status) {
					case "fulfilled": return t.value;
					case "rejected": throw e = t.reason, ro(e), e;
				}
				throw to = t, Ja;
		}
	}
	function eo(e) {
		try {
			var t = e._init;
			return t(e._payload);
		} catch (e) {
			throw typeof e == "object" && e && typeof e.then == "function" ? (to = e, Ja) : e;
		}
	}
	var to = null;
	function no() {
		if (to === null) throw Error(s(459));
		var e = to;
		return to = null, e;
	}
	function ro(e) {
		if (e === Ja || e === Xa) throw Error(s(483));
	}
	var io = null, ao = 0;
	function oo(e) {
		var t = ao;
		return ao += 1, io === null && (io = []), $a(io, e, t);
	}
	function so(e, t) {
		t = t.props.ref, e.ref = t === void 0 ? null : t;
	}
	function co(e, t) {
		throw t.$$typeof === ne ? Error(s(525)) : (e = Object.prototype.toString.call(t), Error(s(31, e === "[object Object]" ? "object with keys {" + Object.keys(t).join(", ") + "}" : e)));
	}
	function lo(e) {
		function t(t, n) {
			if (e) {
				var r = t.deletions;
				r === null ? (t.deletions = [n], t.flags |= 16) : r.push(n);
			}
		}
		function n(n, r) {
			if (!e) return null;
			for (; r !== null;) t(n, r), r = r.sibling;
			return null;
		}
		function r(e) {
			for (var t = /* @__PURE__ */ new Map(); e !== null;) e.key === null ? t.set(e.index, e) : t.set(e.key, e), e = e.sibling;
			return t;
		}
		function i(e, t) {
			return e = Pi(e, t), e.index = 0, e.sibling = null, e;
		}
		function a(t, n, r) {
			return t.index = r, e ? (r = t.alternate, r === null ? (t.flags |= 134217730, n) : (r = r.index, r < n ? (t.flags |= 2, n) : r)) : (t.flags |= 1048576, n);
		}
		function o(t) {
			return e && t.alternate === null && (t.flags |= 134217730), t;
		}
		function c(e, t, n, r) {
			return t === null || t.tag !== 6 ? (t = Ri(n, e.mode, r), t.return = e, t) : (t = i(t, n), t.return = e, t);
		}
		function l(e, t, n, r) {
			var a = n.type;
			return a === E ? (e = d(e, t, n.props.children, r, n.key), so(e, n), e) : t !== null && (t.elementType === a || typeof a == "object" && a && a.$$typeof === de && eo(a) === t.type) ? (t = i(t, n.props), so(t, n), t.return = e, t) : (t = Ii(n.type, n.key, n.props, null, e.mode, r), so(t, n), t.return = e, t);
		}
		function u(e, t, n, r) {
			return t === null || t.tag !== 4 || t.stateNode.containerInfo !== n.containerInfo || t.stateNode.implementation !== n.implementation ? (t = Bi(n, e.mode, r), t.return = e, t) : (t = i(t, n.children || []), t.return = e, t);
		}
		function d(e, t, n, r, a) {
			return t === null || t.tag !== 7 ? (t = Li(n, e.mode, r, a), t.return = e, t) : (t = i(t, n), t.return = e, t);
		}
		function f(e, t, n) {
			if (typeof t == "string" && t !== "" || typeof t == "number" || typeof t == "bigint") return t = Ri("" + t, e.mode, n), t.return = e, t;
			if (typeof t == "object" && t) {
				switch (t.$$typeof) {
					case re: return n = Ii(t.type, t.key, t.props, null, e.mode, n), so(n, t), n.return = e, n;
					case ie: return t = Bi(t, e.mode, n), t.return = e, t;
					case de: return t = eo(t), f(e, t, n);
				}
				if (xe(t) || ve(t)) return t = Li(t, e.mode, n, null), t.return = e, t;
				if (typeof t.then == "function") return f(e, oo(t), n);
				if (t.$$typeof === D) return f(e, Ta(e, t), n);
				co(e, t);
			}
			return null;
		}
		function p(e, t, n, r) {
			var i = t === null ? null : t.key;
			if (typeof n == "string" && n !== "" || typeof n == "number" || typeof n == "bigint") return i === null ? c(e, t, "" + n, r) : null;
			if (typeof n == "object" && n) {
				switch (n.$$typeof) {
					case re: return n.key === i ? l(e, t, n, r) : null;
					case ie: return n.key === i ? u(e, t, n, r) : null;
					case de: return n = eo(n), p(e, t, n, r);
				}
				if (xe(n) || ve(n)) return i === null ? d(e, t, n, r, null) : null;
				if (typeof n.then == "function") return p(e, t, oo(n), r);
				if (n.$$typeof === D) return p(e, t, Ta(e, n), r);
				co(e, n);
			}
			return null;
		}
		function m(e, t, n, r, i) {
			if (typeof r == "string" && r !== "" || typeof r == "number" || typeof r == "bigint") return e = e.get(n) || null, c(t, e, "" + r, i);
			if (typeof r == "object" && r) {
				switch (r.$$typeof) {
					case re: return e = e.get(r.key === null ? n : r.key) || null, l(t, e, r, i);
					case ie: return e = e.get(r.key === null ? n : r.key) || null, u(t, e, r, i);
					case de: return r = eo(r), m(e, t, n, r, i);
				}
				if (xe(r) || ve(r)) return e = e.get(n) || null, d(t, e, r, i, null);
				if (typeof r.then == "function") return m(e, t, n, oo(r), i);
				if (r.$$typeof === D) return m(e, t, n, Ta(t, r), i);
				co(t, r);
			}
			return null;
		}
		function h(i, o, s, c) {
			for (var l = null, u = null, d = o, h = o = 0, g = null; d !== null && h < s.length; h++) {
				d.index > h ? (g = d, d = null) : g = d.sibling;
				var _ = p(i, d, s[h], c);
				if (_ === null) {
					d === null && (d = g);
					break;
				}
				e && d && _.alternate === null && t(i, d), o = a(_, o, h), u === null ? l = _ : u.sibling = _, u = _, d = g;
			}
			if (h === s.length) return n(i, d), V && Qi(i, h), l;
			if (d === null) {
				for (; h < s.length; h++) d = f(i, s[h], c), d !== null && (o = a(d, o, h), u === null ? l = d : u.sibling = d, u = d);
				return V && Qi(i, h), l;
			}
			for (d = r(d); h < s.length; h++) g = m(d, i, h, s[h], c), g !== null && (e && (_ = g.alternate, _ !== null && d.delete(_.key === null ? h : _.key)), o = a(g, o, h), u === null ? l = g : u.sibling = g, u = g);
			return e && d.forEach(function(e) {
				return t(i, e);
			}), V && Qi(i, h), l;
		}
		function g(i, o, c, l) {
			if (c == null) throw Error(s(151));
			for (var u = null, d = null, h = o, g = o = 0, _ = null, v = c.next(); h !== null && !v.done; g++, v = c.next()) {
				h.index > g ? (_ = h, h = null) : _ = h.sibling;
				var y = p(i, h, v.value, l);
				if (y === null) {
					h === null && (h = _);
					break;
				}
				e && h && y.alternate === null && t(i, h), o = a(y, o, g), d === null ? u = y : d.sibling = y, d = y, h = _;
			}
			if (v.done) return n(i, h), V && Qi(i, g), u;
			if (h === null) {
				for (; !v.done; g++, v = c.next()) v = f(i, v.value, l), v !== null && (o = a(v, o, g), d === null ? u = v : d.sibling = v, d = v);
				return V && Qi(i, g), u;
			}
			for (h = r(h); !v.done; g++, v = c.next()) v = m(h, i, g, v.value, l), v !== null && (e && (_ = v.alternate, _ !== null && h.delete(_.key === null ? g : _.key)), o = a(v, o, g), d === null ? u = v : d.sibling = v, d = v);
			return e && h.forEach(function(e) {
				return t(i, e);
			}), V && Qi(i, g), u;
		}
		function _(e, r, a, c) {
			if (typeof a == "object" && a && a.type === E && a.key === null && a.props.ref === void 0 && (a = a.props.children), typeof a == "object" && a) {
				switch (a.$$typeof) {
					case re:
						a: {
							for (var l = a.key; r !== null;) {
								if (r.key === l) {
									if (l = a.type, l === E) {
										if (r.tag === 7) {
											n(e, r.sibling), c = i(r, a.props.children), so(c, a), c.return = e, e = c;
											break a;
										}
									} else if (r.elementType === l || typeof l == "object" && l && l.$$typeof === de && eo(l) === r.type) {
										n(e, r.sibling), c = i(r, a.props), so(c, a), c.return = e, e = c;
										break a;
									}
									n(e, r);
									break;
								}
								t(e, r), r = r.sibling;
							}
							a.type === E ? (c = Li(a.props.children, e.mode, c, a.key), so(c, a), c.return = e, e = c) : (c = Ii(a.type, a.key, a.props, null, e.mode, c), so(c, a), c.return = e, e = c);
						}
						return o(e);
					case ie:
						a: {
							for (l = a.key; r !== null;) {
								if (r.key === l) {
									if (r.tag === 4 && r.stateNode.containerInfo === a.containerInfo && r.stateNode.implementation === a.implementation) {
										n(e, r.sibling), c = i(r, a.children || []), c.return = e, e = c;
										break a;
									}
									n(e, r);
									break;
								}
								t(e, r), r = r.sibling;
							}
							c = Bi(a, e.mode, c), c.return = e, e = c;
						}
						return o(e);
					case de: return a = eo(a), _(e, r, a, c);
				}
				if (xe(a)) return h(e, r, a, c);
				if (ve(a)) {
					if (l = ve(a), typeof l != "function") throw Error(s(150));
					return a = l.call(a), g(e, r, a, c);
				}
				if (typeof a.then == "function") return _(e, r, oo(a), c);
				if (a.$$typeof === D) return _(e, r, Ta(e, a), c);
				co(e, a);
			}
			return typeof a == "string" && a !== "" || typeof a == "number" || typeof a == "bigint" ? (a = "" + a, r !== null && r.tag === 6 ? (n(e, r.sibling), c = i(r, a), c.return = e, e = c) : (n(e, r), c = Ri(a, e.mode, c), c.return = e, e = c), o(e)) : n(e, r);
		}
		return function(e, t, n, r) {
			try {
				ao = 0;
				var i = _(e, t, n, r);
				return io = null, i;
			} catch (t) {
				if (t === Ja || t === Xa) throw t;
				var a = Mi(29, t, null, e.mode);
				return a.lanes = r, a.return = e, a;
			}
		};
	}
	var uo = lo(!0), fo = lo(!1), po = !1;
	function mo(e) {
		e.updateQueue = {
			baseState: e.memoizedState,
			firstBaseUpdate: null,
			lastBaseUpdate: null,
			shared: {
				pending: null,
				lanes: 0,
				hiddenCallbacks: null
			},
			callbacks: null
		};
	}
	function ho(e, t) {
		e = e.updateQueue, t.updateQueue === e && (t.updateQueue = {
			baseState: e.baseState,
			firstBaseUpdate: e.firstBaseUpdate,
			lastBaseUpdate: e.lastBaseUpdate,
			shared: e.shared,
			callbacks: null
		});
	}
	function go(e) {
		return {
			lane: e,
			tag: 0,
			payload: null,
			callback: null,
			next: null
		};
	}
	function _o(e, t, n) {
		var r = e.updateQueue;
		if (r === null) return null;
		if (r = r.shared, K & 2) {
			var i = r.pending;
			return i === null ? t.next = t : (t.next = i.next, i.next = t), r.pending = t, t = ki(e), Oi(e, null, n), t;
		}
		return Ti(e, r, t, n), ki(e);
	}
	function vo(e, t, n) {
		if (t = t.updateQueue, t !== null && (t = t.shared, n & 4194048)) {
			var r = t.lanes;
			r &= e.pendingLanes, n |= r, t.lanes = n, yt(e, n);
		}
	}
	function yo(e, t) {
		var n = e.updateQueue, r = e.alternate;
		if (r !== null && (r = r.updateQueue, n === r)) {
			var i = null, a = null;
			if (n = n.firstBaseUpdate, n !== null) {
				do {
					var o = {
						lane: n.lane,
						tag: n.tag,
						payload: n.payload,
						callback: null,
						next: null
					};
					a === null ? i = a = o : a = a.next = o, n = n.next;
				} while (n !== null);
				a === null ? i = a = t : a = a.next = t;
			} else i = a = t;
			n = {
				baseState: r.baseState,
				firstBaseUpdate: i,
				lastBaseUpdate: a,
				shared: r.shared,
				callbacks: r.callbacks
			}, e.updateQueue = n;
		} else e = n.lastBaseUpdate, e === null ? n.firstBaseUpdate = t : e.next = t, n.lastBaseUpdate = t;
	}
	var bo = !1;
	function xo() {
		if (bo) {
			var e = za;
			if (e !== null) throw e;
		}
	}
	function So(e, t, n, r) {
		bo = !1;
		var i = e.updateQueue;
		po = !1;
		var a = i.firstBaseUpdate, o = i.lastBaseUpdate, s = i.shared.pending;
		if (s !== null) {
			i.shared.pending = null;
			var c = s, l = c.next;
			c.next = null, o === null ? a = l : o.next = l, o = c;
			var u = e.alternate;
			u !== null && (u = u.updateQueue, s = u.lastBaseUpdate, s !== o && (s === null ? u.firstBaseUpdate = l : s.next = l, u.lastBaseUpdate = c));
		}
		if (a !== null) {
			var d = i.baseState;
			o = 0, u = l = c = null, s = a;
			do {
				var f = s.lane & -536870913, p = f !== s.lane;
				if (p ? (Y & f) === f : (r & f) === f) {
					f !== 0 && f === Ra && (bo = !0), u !== null && (u = u.next = {
						lane: 0,
						tag: s.tag,
						payload: s.payload,
						callback: null,
						next: null
					});
					a: {
						var m = e, h = s;
						f = t;
						var g = n;
						switch (h.tag) {
							case 1:
								if (m = h.payload, typeof m == "function") {
									d = m.call(g, d, f);
									break a;
								}
								d = m;
								break a;
							case 3: m.flags = m.flags & -65537 | 128;
							case 0:
								if (m = h.payload, f = typeof m == "function" ? m.call(g, d, f) : m, f == null) break a;
								d = T({}, d, f);
								break a;
							case 2: po = !0;
						}
					}
					f = s.callback, f !== null && (e.flags |= 64, p && (e.flags |= 8192), p = i.callbacks, p === null ? i.callbacks = [f] : p.push(f));
				} else p = {
					lane: f,
					tag: s.tag,
					payload: s.payload,
					callback: s.callback,
					next: null
				}, u === null ? (l = u = p, c = d) : u = u.next = p, o |= f;
				if (s = s.next, s === null) {
					if (s = i.shared.pending, s === null) break;
					p = s, s = p.next, p.next = null, i.lastBaseUpdate = p, i.shared.pending = null;
				}
			} while (1);
			u === null && (c = d), i.baseState = c, i.firstBaseUpdate = l, i.lastBaseUpdate = u, a === null && (i.shared.lanes = 0), od |= o, e.lanes = o, e.memoizedState = d;
		}
	}
	function Co(e, t) {
		if (typeof e != "function") throw Error(s(191, e));
		e.call(t);
	}
	function wo(e, t) {
		var n = e.callbacks;
		if (n !== null) for (e.callbacks = null, e = 0; e < n.length; e++) Co(n[e], t);
	}
	var To = Te(null), Eo = Te(0);
	function Do(e, t) {
		e = id, j(Eo, e), j(To, t), id = e | t.baseLanes;
	}
	function Oo() {
		j(Eo, id), j(To, To.current);
	}
	function ko() {
		id = Eo.current, Ee(To), Ee(Eo);
	}
	var Ao = Te(null), jo = null;
	function Mo(e) {
		var t = e.alternate;
		j(Lo, Lo.current & 1), j(Ao, e), jo === null && (t === null || To.current !== null || t.memoizedState !== null) && (jo = e);
	}
	function No(e) {
		j(Lo, Lo.current), j(Ao, e), jo === null && (jo = e);
	}
	function Po(e) {
		e.tag === 22 ? (j(Lo, Lo.current), j(Ao, e), jo === null && (jo = e)) : Fo();
	}
	function Fo() {
		j(Lo, Lo.current), j(Ao, Ao.current);
	}
	function Io(e) {
		Ee(Ao), jo === e && (jo = null), Ee(Lo);
	}
	var Lo = Te(0);
	function Ro(e, t) {
		j(Ao, Ao.current), j(Lo, t);
	}
	function zo(e) {
		Ee(Lo), Ee(Ao), jo === e && (jo = null);
	}
	function Bo(e) {
		for (var t = e; t !== null;) {
			if (t.tag === 13) {
				var n = t.memoizedState;
				if (n !== null && (n = n.dehydrated, n === null || om(n) || sm(n))) return t;
			} else if (t.tag === 19 && t.memoizedProps.revealOrder !== "independent") {
				if (t.flags & 128) return t;
			} else if (t.child !== null) {
				t.child.return = t, t = t.child;
				continue;
			}
			if (t === e) break;
			for (; t.sibling === null;) {
				if (t.return === null || t.return === e) return null;
				t = t.return;
			}
			t.sibling.return = t.return, t = t.sibling;
		}
		return null;
	}
	var Vo = 0, H = null, U = null, Ho = null, Uo = !1, Wo = !1, Go = !1, Ko = 0, qo = 0, Jo = null, Yo = 0;
	function Xo() {
		throw Error(s(321));
	}
	function Zo(e, t) {
		if (t === null) return !1;
		for (var n = 0; n < t.length && n < e.length; n++) if (!Vr(e[n], t[n])) return !1;
		return !0;
	}
	function Qo(e, t, n, r, i, a) {
		return Vo = a, H = t, t.memoizedState = null, t.updateQueue = null, t.lanes = 0, k.H = e === null || e.memoizedState === null ? hc : gc, Go = !1, a = n(r, i), Go = !1, Wo && (a = es(t, n, r, i)), $o(e), a;
	}
	function $o(e) {
		k.H = mc;
		var t = U !== null && U.next !== null;
		if (Vo = 0, Ho = U = H = null, Uo = !1, qo = 0, Jo = null, t) throw Error(s(300));
		e === null || Nc || (e = e.dependencies, e !== null && Sa(e) && (Nc = !0));
	}
	function es(e, t, n, r) {
		H = e;
		var i = 0;
		do {
			if (Wo && (Jo = null), qo = 0, Wo = !1, 25 <= i) throw Error(s(301));
			if (i += 1, Ho = U = null, e.updateQueue != null) {
				var a = e.updateQueue;
				a.lastEffect = null, a.events = null, a.stores = null, a.memoCache != null && (a.memoCache.index = 0);
			}
			k.H = _c, a = t(n, r);
		} while (Wo);
		return a;
	}
	function ts() {
		var e = k.H, t = e.useState()[0];
		return t = typeof t.then == "function" ? cs(t) : t, e = e.useState()[0], (U === null ? null : U.memoizedState) !== e && (H.flags |= 1024), t;
	}
	function ns() {
		var e = Ko !== 0;
		return Ko = 0, e;
	}
	function rs(e, t, n) {
		t.updateQueue = e.updateQueue, t.flags &= -2053, e.lanes &= ~n;
	}
	function is(e) {
		if (Uo) {
			for (e = e.memoizedState; e !== null;) {
				var t = e.queue;
				t !== null && (t.pending = null), e = e.next;
			}
			Uo = !1;
		}
		Vo = 0, Ho = U = H = null, Wo = !1, qo = Ko = 0, Jo = null;
	}
	function as() {
		var e = {
			memoizedState: null,
			baseState: null,
			baseQueue: null,
			queue: null,
			next: null
		};
		return Ho === null ? H.memoizedState = Ho = e : Ho = Ho.next = e, Ho;
	}
	function os() {
		if (U === null) {
			var e = H.alternate;
			e = e === null ? null : e.memoizedState;
		} else e = U.next;
		var t = Ho === null ? H.memoizedState : Ho.next;
		if (t !== null) Ho = t, U = e;
		else {
			if (e === null) throw H.alternate === null ? Error(s(467)) : Error(s(310));
			U = e, e = {
				memoizedState: U.memoizedState,
				baseState: U.baseState,
				baseQueue: U.baseQueue,
				queue: U.queue,
				next: null
			}, Ho === null ? H.memoizedState = Ho = e : Ho = Ho.next = e;
		}
		return Ho;
	}
	function ss() {
		return {
			lastEffect: null,
			events: null,
			stores: null,
			memoCache: null
		};
	}
	function cs(e) {
		var t = qo;
		return qo += 1, Jo === null && (Jo = []), e = $a(Jo, e, t), t = H, (Ho === null ? t.memoizedState : Ho.next) === null && (t = t.alternate, k.H = t === null || t.memoizedState === null ? hc : gc), e;
	}
	function ls(e) {
		if (typeof e == "object" && e) {
			if (typeof e.then == "function") return cs(e);
			if (e.$$typeof === ge) return;
			if (e.$$typeof === D) return wa(e);
		}
		throw Error(s(438, String(e)));
	}
	function us(e) {
		var t = null, n = H.updateQueue;
		if (n !== null && (t = n.memoCache), t == null) {
			var r = H.alternate;
			r !== null && (r = r.updateQueue, r !== null && (r = r.memoCache, r != null && (t = {
				data: r.data.map(function(e) {
					return e.slice();
				}),
				index: 0
			})));
		}
		if (t ??= {
			data: [],
			index: 0
		}, n === null && (n = ss(), H.updateQueue = n), n.memoCache = t, n = t.data[t.index], n === void 0) for (n = t.data[t.index] = Array(e), r = 0; r < e; r++) n[r] = me;
		return t.index++, n;
	}
	function ds(e, t) {
		return typeof t == "function" ? t(e) : t;
	}
	function fs(e) {
		return ps(os(), U, e);
	}
	function ps(e, t, n) {
		var r = e.queue;
		if (r === null) throw Error(s(311));
		r.lastRenderedReducer = n;
		var i = e.baseQueue, a = r.pending;
		if (a !== null) {
			if (i !== null) {
				var o = i.next;
				i.next = a.next, a.next = o;
			}
			t.baseQueue = i = a, r.pending = null;
		}
		if (a = e.baseState, i === null) e.memoizedState = a;
		else {
			t = i.next;
			var c = o = null, l = null, u = t, d = !1;
			do {
				var f = u.lane & -536870913;
				if (f === u.lane ? (Vo & f) === f : (Y & f) === f) {
					var p = u.revertLane;
					if (p === 0) l !== null && (l = l.next = {
						lane: 0,
						revertLane: 0,
						gesture: null,
						action: u.action,
						hasEagerState: u.hasEagerState,
						eagerState: u.eagerState,
						next: null
					}), f === Ra && (d = !0);
					else if ((Vo & p) === p) {
						u = u.next, p === Ra && (d = !0);
						continue;
					} else f = {
						lane: 0,
						revertLane: u.revertLane,
						gesture: null,
						action: u.action,
						hasEagerState: u.hasEagerState,
						eagerState: u.eagerState,
						next: null
					}, l === null ? (c = l = f, o = a) : l = l.next = f, H.lanes |= p, od |= p;
					f = u.action, Go && n(a, f), a = u.hasEagerState ? u.eagerState : n(a, f);
				} else p = {
					lane: f,
					revertLane: u.revertLane,
					gesture: u.gesture,
					action: u.action,
					hasEagerState: u.hasEagerState,
					eagerState: u.eagerState,
					next: null
				}, l === null ? (c = l = p, o = a) : l = l.next = p, H.lanes |= f, od |= f;
				u = u.next;
			} while (u !== null && u !== t);
			if (l === null ? o = a : l.next = c, !Vr(a, e.memoizedState) && (Nc = !0, d && (n = za, n !== null))) throw n;
			e.memoizedState = a, e.baseState = o, e.baseQueue = l, r.lastRenderedState = a;
		}
		return i === null && (r.lanes = 0), [e.memoizedState, r.dispatch];
	}
	function ms(e) {
		var t = os(), n = t.queue;
		if (n === null) throw Error(s(311));
		n.lastRenderedReducer = e;
		var r = n.dispatch, i = n.pending, a = t.memoizedState;
		if (i !== null) {
			n.pending = null;
			var o = i = i.next;
			do
				a = e(a, o.action), o = o.next;
			while (o !== i);
			Vr(a, t.memoizedState) || (Nc = !0), t.memoizedState = a, t.baseQueue === null && (t.baseState = a), n.lastRenderedState = a;
		}
		return [a, r];
	}
	function hs(e, t, n) {
		var r = H, i = os(), a = V;
		if (a) {
			if (n === void 0) throw Error(s(407));
			n = n();
		} else n = t();
		var o = !Vr((U || i).memoizedState, n);
		if (o && (i.memoizedState = n, Nc = !0), i = i.queue, Bs(vs.bind(null, r, i, e), [e]), e = i.getSnapshot !== t || o || Ho !== null && !!(Ho.memoizedState.tag & 1), Fs(e ? 9 : 8, { destroy: void 0 }, _s.bind(null, r, i, n, t), null), e) {
			if (r.flags |= 2048, q === null) throw Error(s(349));
			a || Vo & 127 || gs(r, t, n);
		}
		return n;
	}
	function gs(e, t, n) {
		e.flags |= 16384, e = {
			getSnapshot: t,
			value: n
		}, t = H.updateQueue, t === null ? (t = ss(), H.updateQueue = t, t.stores = [e]) : (n = t.stores, n === null ? t.stores = [e] : n.push(e));
	}
	function _s(e, t, n, r) {
		t.value = n, t.getSnapshot = r, ys(t) && bs(e);
	}
	function vs(e, t, n) {
		return n(function() {
			ys(t) && bs(e);
		});
	}
	function ys(e) {
		var t = e.getSnapshot;
		e = e.value;
		try {
			var n = t();
			return !Vr(e, n);
		} catch {
			return !0;
		}
	}
	function bs(e) {
		var t = Di(e, 2);
		t !== null && Pd(t, e, 2);
	}
	function xs(e) {
		var t = as();
		if (typeof e == "function") {
			var n = e;
			if (e = n(), Go) {
				nt(!0);
				try {
					n();
				} finally {
					nt(!1);
				}
			}
		}
		return t.memoizedState = t.baseState = e, t.queue = {
			pending: null,
			lanes: 0,
			dispatch: null,
			lastRenderedReducer: ds,
			lastRenderedState: e
		}, t;
	}
	function Ss(e, t, n, r) {
		return e.baseState = n, ps(e, U, typeof r == "function" ? r : ds);
	}
	function Cs(e, t, n, r, i) {
		if (dc(e)) throw Error(s(485));
		if (e = t.action, e !== null) {
			var a = {
				payload: i,
				action: e,
				next: null,
				isTransition: !0,
				status: "pending",
				value: null,
				reason: null,
				listeners: [],
				then: function(e) {
					a.listeners.push(e);
				}
			};
			k.T === null ? a.isTransition = !1 : n(!0), r(a), n = t.pending, n === null ? (a.next = t.pending = a, ws(t, a)) : (a.next = n.next, t.pending = n.next = a);
		}
	}
	function ws(e, t) {
		var n = t.action, r = t.payload, i = e.state;
		if (t.isTransition) {
			var a = k.T, o = {};
			o.types = a === null ? null : a.types, k.T = o;
			try {
				var s = n(i, r), c = k.S;
				c !== null && c(o, s), Ts(e, t, s);
			} catch (n) {
				Ds(e, t, n);
			} finally {
				a !== null && o.types !== null && (a.types = o.types), k.T = a;
			}
		} else try {
			a = n(i, r), Ts(e, t, a);
		} catch (n) {
			Ds(e, t, n);
		}
	}
	function Ts(e, t, n) {
		typeof n == "object" && n && typeof n.then == "function" ? n.then(function(n) {
			Es(e, t, n);
		}, function(n) {
			return Ds(e, t, n);
		}) : Es(e, t, n);
	}
	function Es(e, t, n) {
		t.status = "fulfilled", t.value = n, Os(t), e.state = n, t = e.pending, t !== null && (n = t.next, n === t ? e.pending = null : (n = n.next, t.next = n, ws(e, n)));
	}
	function Ds(e, t, n) {
		var r = e.pending;
		if (e.pending = null, r !== null) {
			r = r.next;
			do
				t.status = "rejected", t.reason = n, Os(t), t = t.next;
			while (t !== r);
		}
		e.action = null;
	}
	function Os(e) {
		e = e.listeners;
		for (var t = 0; t < e.length; t++) (0, e[t])();
	}
	function ks(e, t) {
		return t;
	}
	function As(e, t) {
		if (V) {
			var n = q.formState;
			if (n !== null) {
				a: {
					var r = H;
					if (V) {
						if (B) {
							b: {
								for (var i = B, a = aa; i.nodeType !== 8;) if (!a || (i = lm(i.nextSibling), i === null)) {
									i = null;
									break b;
								}
								a = i.data, i = a === "F!" || a === "F" ? i : null;
							}
							if (i) {
								B = lm(i.nextSibling), r = i.data === "F!";
								break a;
							}
						}
						sa(r);
					}
					r = !1;
				}
				r && (t = n[0]);
			}
		}
		return n = as(), n.memoizedState = n.baseState = t, r = {
			pending: null,
			lanes: 0,
			dispatch: null,
			lastRenderedReducer: ks,
			lastRenderedState: t
		}, n.queue = r, n = cc.bind(null, H, r), r.dispatch = n, r = xs(!1), a = uc.bind(null, H, !1, r.queue), r = as(), i = {
			state: t,
			dispatch: null,
			action: e,
			pending: null
		}, r.queue = i, n = Cs.bind(null, H, i, a, n), i.dispatch = n, r.memoizedState = e, [
			t,
			n,
			!1
		];
	}
	function js(e) {
		return Ms(os(), U, e);
	}
	function Ms(e, t, n) {
		if (t = ps(e, t, ks)[0], e = fs(ds)[0], typeof t == "object" && t && typeof t.then == "function") try {
			var r = cs(t);
		} catch (e) {
			throw e === Ja ? Xa : e;
		}
		else r = t;
		t = os();
		var i = t.queue, a = i.dispatch;
		return n !== t.memoizedState && (H.flags |= 2048, Fs(9, { destroy: void 0 }, Ns.bind(null, i, n), null)), [
			r,
			a,
			e
		];
	}
	function Ns(e, t) {
		e.action = t;
	}
	function Ps(e) {
		var t = os(), n = U;
		if (n !== null) return Ms(t, n, e);
		os(), t = t.memoizedState, n = os();
		var r = n.queue.dispatch;
		return n.memoizedState = e, [
			t,
			r,
			!1
		];
	}
	function Fs(e, t, n, r) {
		return e = {
			tag: e,
			create: n,
			deps: r,
			inst: t,
			next: null
		}, t = H.updateQueue, t === null && (t = ss(), H.updateQueue = t), n = t.lastEffect, n === null ? t.lastEffect = e.next = e : (r = n.next, n.next = e, e.next = r, t.lastEffect = e), e;
	}
	function Is() {
		return os().memoizedState;
	}
	function Ls(e, t, n, r) {
		var i = as();
		H.flags |= e, i.memoizedState = Fs(1 | t, { destroy: void 0 }, n, r === void 0 ? null : r);
	}
	function Rs(e, t, n, r) {
		var i = os();
		r = r === void 0 ? null : r;
		var a = i.memoizedState.inst;
		U !== null && r !== null && Zo(r, U.memoizedState.deps) ? i.memoizedState = Fs(t, a, n, r) : (H.flags |= e, i.memoizedState = Fs(1 | t, a, n, r));
	}
	function zs(e, t) {
		Ls(8390656, 8, e, t);
	}
	function Bs(e, t) {
		Rs(2048, 8, e, t);
	}
	function Vs(e) {
		H.flags |= 4;
		var t = H.updateQueue;
		if (t === null) t = ss(), H.updateQueue = t, t.events = [e];
		else {
			var n = t.events;
			n === null ? t.events = [e] : n.push(e);
		}
	}
	function Hs(e) {
		var t = os().memoizedState;
		return Vs({
			ref: t,
			nextImpl: e
		}), function() {
			if (K & 2) throw Error(s(440));
			return t.impl.apply(void 0, arguments);
		};
	}
	function Us(e, t) {
		return Rs(4, 2, e, t);
	}
	function Ws(e, t) {
		return Rs(4, 4, e, t);
	}
	function Gs(e, t) {
		if (typeof t == "function") {
			e = e();
			var n = t(e);
			return function() {
				typeof n == "function" ? n() : t(null);
			};
		}
		if (t != null) return e = e(), t.current = e, function() {
			t.current = null;
		};
	}
	function Ks(e, t, n) {
		n = n == null ? null : n.concat([e]), Rs(4, 4, Gs.bind(null, t, e), n);
	}
	function qs() {}
	function Js(e, t) {
		var n = os();
		t = t === void 0 ? null : t;
		var r = n.memoizedState;
		return t !== null && Zo(t, r[1]) ? r[0] : (n.memoizedState = [e, t], e);
	}
	function Ys(e, t) {
		var n = os();
		t = t === void 0 ? null : t;
		var r = n.memoizedState;
		if (t !== null && Zo(t, r[1])) return r[0];
		if (r = e(), Go) {
			nt(!0);
			try {
				e();
			} finally {
				nt(!1);
			}
		}
		return n.memoizedState = [r, t], r;
	}
	function Xs(e, t, n) {
		return n === void 0 || Vo & 1073741824 && !(Y & 261930) ? e.memoizedState = t : (e.memoizedState = n, e = Md(), H.lanes |= e, od |= e, n);
	}
	function Zs(e, t, n, r) {
		return Vr(n, t) ? n : To.current === null ? !(Vo & 106) || Vo & 1073741824 && !(Y & 261930) ? (Nc = !0, e.memoizedState = n) : (e = Md(), H.lanes |= e, od |= e, t) : (e = Xs(e, n, r), Vr(e, t) || (Nc = !0), e);
	}
	function Qs(e, t, n, r, i) {
		var a = A.p;
		A.p = a !== 0 && 8 > a ? a : 8;
		var o = k.T, s = {};
		s.types = o === null ? null : o.types, k.T = s, uc(e, !1, t, n);
		try {
			var c = i(), l = k.S;
			l !== null && l(s, c), typeof c == "object" && c && typeof c.then == "function" ? lc(e, t, Ha(c, r), jd(e)) : lc(e, t, r, jd(e));
		} catch (n) {
			lc(e, t, {
				then: function() {},
				status: "rejected",
				reason: n
			}, jd());
		} finally {
			A.p = a, o !== null && s.types !== null && (o.types = s.types), k.T = o;
		}
	}
	function $s() {}
	function ec(e, t, n, r) {
		if (e.tag !== 5) throw Error(s(476));
		var i = tc(e).queue;
		Qs(e, i, t, Se, n === null ? $s : function() {
			return nc(e), n(r);
		});
	}
	function tc(e) {
		var t = e.memoizedState;
		if (t !== null) return t;
		t = {
			memoizedState: Se,
			baseState: Se,
			baseQueue: null,
			queue: {
				pending: null,
				lanes: 0,
				dispatch: null,
				lastRenderedReducer: ds,
				lastRenderedState: Se
			},
			next: null
		};
		var n = {};
		return t.next = {
			memoizedState: n,
			baseState: n,
			baseQueue: null,
			queue: {
				pending: null,
				lanes: 0,
				dispatch: null,
				lastRenderedReducer: ds,
				lastRenderedState: n
			},
			next: null
		}, e.memoizedState = t, e = e.alternate, e !== null && (e.memoizedState = t), t;
	}
	function nc(e) {
		var t = tc(e);
		t.next === null && (t = e.alternate.memoizedState), lc(e, t.next.queue, {}, jd());
	}
	function rc() {
		return wa(sh);
	}
	function ic() {
		return os().memoizedState;
	}
	function ac() {
		return os().memoizedState;
	}
	function oc(e) {
		for (var t = e.return; t !== null;) {
			switch (t.tag) {
				case 24:
				case 3:
					var n = jd();
					e = go(n);
					var r = _o(t, e, n);
					r !== null && (Pd(r, t, n), vo(r, t, n)), t = { cache: ja() }, e.payload = t;
					return;
			}
			t = t.return;
		}
	}
	function sc(e, t, n) {
		var r = jd();
		n = {
			lane: r,
			revertLane: 0,
			gesture: null,
			action: n,
			hasEagerState: !1,
			eagerState: null,
			next: null
		}, dc(e) ? fc(t, n) : (n = Ei(e, t, n, r), n !== null && (Pd(n, e, r), pc(n, t, r)));
	}
	function cc(e, t, n) {
		lc(e, t, n, jd());
	}
	function lc(e, t, n, r) {
		var i = {
			lane: r,
			revertLane: 0,
			gesture: null,
			action: n,
			hasEagerState: !1,
			eagerState: null,
			next: null
		};
		if (dc(e)) fc(t, i);
		else {
			var a = e.alternate;
			if (e.lanes === 0 && (a === null || a.lanes === 0) && (a = t.lastRenderedReducer, a !== null)) try {
				var o = t.lastRenderedState, s = a(o, n);
				if (i.hasEagerState = !0, i.eagerState = s, Vr(s, o)) return Ti(e, t, i, 0), q === null && wi(), !1;
			} catch {}
			if (n = Ei(e, t, i, r), n !== null) return Pd(n, e, r), pc(n, t, r), !0;
		}
		return !1;
	}
	function uc(e, t, n, r) {
		if (r = {
			lane: 2,
			revertLane: Pf(),
			gesture: null,
			action: r,
			hasEagerState: !1,
			eagerState: null,
			next: null
		}, dc(e)) {
			if (t) throw Error(s(479));
		} else t = Ei(e, n, r, 2), t !== null && Pd(t, e, 2);
	}
	function dc(e) {
		var t = e.alternate;
		return e === H || t !== null && t === H;
	}
	function fc(e, t) {
		Wo = Uo = !0;
		var n = e.pending;
		n === null ? t.next = t : (t.next = n.next, n.next = t), e.pending = t;
	}
	function pc(e, t, n) {
		if (n & 4194048) {
			var r = t.lanes;
			r &= e.pendingLanes, n |= r, t.lanes = n, yt(e, n);
		}
	}
	var mc = {
		readContext: wa,
		use: ls,
		useCallback: Xo,
		useContext: Xo,
		useEffect: Xo,
		useImperativeHandle: Xo,
		useLayoutEffect: Xo,
		useInsertionEffect: Xo,
		useMemo: Xo,
		useReducer: Xo,
		useRef: Xo,
		useState: Xo,
		useDebugValue: Xo,
		useDeferredValue: Xo,
		useTransition: Xo,
		useSyncExternalStore: Xo,
		useId: Xo,
		useHostTransitionStatus: Xo,
		useFormState: Xo,
		useActionState: Xo,
		useOptimistic: Xo,
		useMemoCache: Xo,
		useCacheRefresh: Xo,
		useEffectEvent: Xo
	}, hc = {
		readContext: wa,
		use: ls,
		useCallback: function(e, t) {
			return as().memoizedState = [e, t === void 0 ? null : t], e;
		},
		useContext: wa,
		useEffect: zs,
		useImperativeHandle: function(e, t, n) {
			n = n == null ? null : n.concat([e]), Ls(4194308, 4, Gs.bind(null, t, e), n);
		},
		useLayoutEffect: function(e, t) {
			return Ls(4194308, 4, e, t);
		},
		useInsertionEffect: function(e, t) {
			Ls(4, 2, e, t);
		},
		useMemo: function(e, t) {
			var n = as();
			t = t === void 0 ? null : t;
			var r = e();
			if (Go) {
				nt(!0);
				try {
					e();
				} finally {
					nt(!1);
				}
			}
			return n.memoizedState = [r, t], r;
		},
		useReducer: function(e, t, n) {
			var r = as();
			if (n !== void 0) {
				var i = n(t);
				if (Go) {
					nt(!0);
					try {
						n(t);
					} finally {
						nt(!1);
					}
				}
			} else i = t;
			return r.memoizedState = r.baseState = i, e = {
				pending: null,
				lanes: 0,
				dispatch: null,
				lastRenderedReducer: e,
				lastRenderedState: i
			}, r.queue = e, e = e.dispatch = sc.bind(null, H, e), [r.memoizedState, e];
		},
		useRef: function(e) {
			var t = as();
			return e = { current: e }, t.memoizedState = e;
		},
		useState: function(e) {
			e = xs(e);
			var t = e.queue, n = cc.bind(null, H, t);
			return t.dispatch = n, [e.memoizedState, n];
		},
		useDebugValue: qs,
		useDeferredValue: function(e, t) {
			return Xs(as(), e, t);
		},
		useTransition: function() {
			var e = xs(!1);
			return e = Qs.bind(null, H, e.queue, !0, !1), as().memoizedState = e, [!1, e];
		},
		useSyncExternalStore: function(e, t, n) {
			var r = H, i = as();
			if (V) {
				if (n === void 0) throw Error(s(407));
				n = n();
			} else {
				if (n = t(), q === null) throw Error(s(349));
				Y & 127 || gs(r, t, n);
			}
			i.memoizedState = n;
			var a = {
				value: n,
				getSnapshot: t
			};
			return i.queue = a, zs(vs.bind(null, r, a, e), [e]), r.flags |= 2048, Fs(9, { destroy: void 0 }, _s.bind(null, r, a, n, t), null), n;
		},
		useId: function() {
			var e = as(), t = q.identifierPrefix;
			if (V) {
				var n = Zi, r = Xi;
				n = (r & ~(1 << 32 - rt(r) - 1)).toString(32) + n, t = "_" + t + "R_" + n, n = Ko++, 0 < n && (t += "H" + n.toString(32)), t += "_";
			} else n = Yo++, t = "_" + t + "r_" + n.toString(32) + "_";
			return e.memoizedState = t;
		},
		useHostTransitionStatus: rc,
		useFormState: As,
		useActionState: As,
		useOptimistic: function(e) {
			var t = as();
			t.memoizedState = t.baseState = e;
			var n = {
				pending: null,
				lanes: 0,
				dispatch: null,
				lastRenderedReducer: null,
				lastRenderedState: null
			};
			return t.queue = n, t = uc.bind(null, H, !0, n), n.dispatch = t, [e, t];
		},
		useMemoCache: us,
		useCacheRefresh: function() {
			return as().memoizedState = oc.bind(null, H);
		},
		useEffectEvent: function(e) {
			var t = as(), n = { impl: e };
			return t.memoizedState = n, function() {
				if (K & 2) throw Error(s(440));
				return n.impl.apply(void 0, arguments);
			};
		}
	}, gc = {
		readContext: wa,
		use: ls,
		useCallback: Js,
		useContext: wa,
		useEffect: Bs,
		useImperativeHandle: Ks,
		useInsertionEffect: Us,
		useLayoutEffect: Ws,
		useMemo: Ys,
		useReducer: fs,
		useRef: Is,
		useState: function() {
			return fs(ds);
		},
		useDebugValue: qs,
		useDeferredValue: function(e, t) {
			return Zs(os(), U.memoizedState, e, t);
		},
		useTransition: function() {
			var e = fs(ds)[0], t = os().memoizedState;
			return [typeof e == "boolean" ? e : cs(e), t];
		},
		useSyncExternalStore: hs,
		useId: ic,
		useHostTransitionStatus: rc,
		useFormState: js,
		useActionState: js,
		useOptimistic: function(e, t) {
			return Ss(os(), U, e, t);
		},
		useMemoCache: us,
		useCacheRefresh: ac,
		useEffectEvent: Hs
	}, _c = {
		readContext: wa,
		use: ls,
		useCallback: Js,
		useContext: wa,
		useEffect: Bs,
		useImperativeHandle: Ks,
		useInsertionEffect: Us,
		useLayoutEffect: Ws,
		useMemo: Ys,
		useReducer: ms,
		useRef: Is,
		useState: function() {
			return ms(ds);
		},
		useDebugValue: qs,
		useDeferredValue: function(e, t) {
			var n = os();
			return U === null ? Xs(n, e, t) : Zs(n, U.memoizedState, e, t);
		},
		useTransition: function() {
			var e = ms(ds)[0], t = os().memoizedState;
			return [typeof e == "boolean" ? e : cs(e), t];
		},
		useSyncExternalStore: hs,
		useId: ic,
		useHostTransitionStatus: rc,
		useFormState: Ps,
		useActionState: Ps,
		useOptimistic: function(e, t) {
			var n = os();
			return U === null ? (n.baseState = e, [e, n.queue.dispatch]) : Ss(n, U, e, t);
		},
		useMemoCache: us,
		useCacheRefresh: ac,
		useEffectEvent: Hs
	};
	function vc(e, t, n, r) {
		t = e.memoizedState, n = n(r, t), n = n == null ? t : T({}, t, n), e.memoizedState = n, e.lanes === 0 && (e.updateQueue.baseState = n);
	}
	var yc = {
		enqueueSetState: function(e, t, n) {
			e = e._reactInternals;
			var r = jd(), i = go(r);
			i.payload = t, n != null && (i.callback = n), t = _o(e, i, r), t !== null && (Pd(t, e, r), vo(t, e, r));
		},
		enqueueReplaceState: function(e, t, n) {
			e = e._reactInternals;
			var r = jd(), i = go(r);
			i.tag = 1, i.payload = t, n != null && (i.callback = n), t = _o(e, i, r), t !== null && (Pd(t, e, r), vo(t, e, r));
		},
		enqueueForceUpdate: function(e, t) {
			e = e._reactInternals;
			var n = jd(), r = go(n);
			r.tag = 2, t != null && (r.callback = t), t = _o(e, r, n), t !== null && (Pd(t, e, n), vo(t, e, n));
		}
	};
	function bc(e, t, n, r, i, a, o) {
		return e = e.stateNode, typeof e.shouldComponentUpdate == "function" ? e.shouldComponentUpdate(r, a, o) : t.prototype && t.prototype.isPureReactComponent ? !Hr(n, r) || !Hr(i, a) : !0;
	}
	function xc(e, t, n, r) {
		e = t.state, typeof t.componentWillReceiveProps == "function" && t.componentWillReceiveProps(n, r), typeof t.UNSAFE_componentWillReceiveProps == "function" && t.UNSAFE_componentWillReceiveProps(n, r), t.state !== e && yc.enqueueReplaceState(t, t.state, null);
	}
	function Sc(e, t) {
		var n = t;
		if ("ref" in t) for (var r in n = {}, t) r !== "ref" && (n[r] = t[r]);
		if (e = e.defaultProps) for (var i in n === t && (n = T({}, n)), e) n[i] === void 0 && (n[i] = e[i]);
		return n;
	}
	function Cc(e) {
		bi(e);
	}
	function wc(e) {
		console.error(e);
	}
	function Tc(e) {
		bi(e);
	}
	function Ec(e, t) {
		try {
			var n = e.onUncaughtError;
			n(t.value, { componentStack: t.stack });
		} catch (e) {
			setTimeout(function() {
				throw e;
			});
		}
	}
	function Dc(e, t, n) {
		try {
			var r = e.onCaughtError;
			r(n.value, {
				componentStack: n.stack,
				errorBoundary: t.tag === 1 ? t.stateNode : null
			});
		} catch (e) {
			setTimeout(function() {
				throw e;
			});
		}
	}
	function Oc(e, t, n) {
		return n = go(n), n.tag = 3, n.payload = { element: null }, n.callback = function() {
			Ec(e, t);
		}, n;
	}
	function kc(e) {
		return e = go(e), e.tag = 3, e;
	}
	function Ac(e, t, n, r) {
		var i = n.type.getDerivedStateFromError;
		if (typeof i == "function") {
			var a = r.value;
			e.payload = function() {
				return i(a);
			}, e.callback = function() {
				Dc(t, n, r);
			};
		}
		var o = n.stateNode;
		o !== null && typeof o.componentDidCatch == "function" && (e.callback = function() {
			Dc(t, n, r), typeof i != "function" && (vd === null ? vd = /* @__PURE__ */ new Set([this]) : vd.add(this));
			var e = r.stack;
			this.componentDidCatch(r.value, { componentStack: e === null ? "" : e });
		});
	}
	function jc(e, t, n, r, i) {
		if (n.flags |= 32768, typeof r == "object" && r && typeof r.then == "function") {
			if (t = n.alternate, t !== null && xa(t, n, i, !0), n = Ao.current, n !== null) {
				switch (n.tag) {
					case 31:
					case 13:
					case 19: return jo === null ? Kd() : n.alternate === null && ad === 0 && (ad = 3), n.flags &= -257, n.flags |= 65536, n.lanes = i, r === Za ? n.flags |= 16384 : (t = n.updateQueue, t === null ? n.updateQueue = /* @__PURE__ */ new Set([r]) : t.add(r), mf(e, r, i)), !1;
					case 22: return n.flags |= 65536, r === Za ? n.flags |= 16384 : (t = n.updateQueue, t === null ? (t = {
						transitions: null,
						markerInstances: null,
						retryQueue: /* @__PURE__ */ new Set([r])
					}, n.updateQueue = t) : (n = t.retryQueue, n === null ? t.retryQueue = /* @__PURE__ */ new Set([r]) : n.add(r)), mf(e, r, i)), !1;
				}
				throw Error(s(435, n.tag));
			}
			return mf(e, r, i), Kd(), !1;
		}
		if (V) return t = Ao.current, t === null ? (r !== oa && (t = Error(s(423), { cause: r }), pa(Hi(t, n))), e = e.current.alternate, e.flags |= 65536, i &= -i, e.lanes |= i, r = Hi(r, n), i = Oc(e.stateNode, r, i), yo(e, i), ad !== 4 && (ad = 2)) : (!(t.flags & 65536) && (t.flags |= 256), t.flags |= 65536, t.lanes = i, r !== oa && (e = Error(s(422), { cause: r }), pa(Hi(e, n)))), !1;
		var a = Error(s(520), { cause: r });
		if (a = Hi(a, n), dd === null ? dd = [a] : dd.push(a), ad !== 4 && (ad = 2), t === null) return !0;
		r = Hi(r, n), n = t;
		do {
			switch (n.tag) {
				case 3: return n.flags |= 65536, e = i & -i, n.lanes |= e, e = Oc(n.stateNode, r, e), yo(n, e), !1;
				case 1:
					if (t = n.type, a = n.stateNode, !(n.flags & 128) && (typeof t.getDerivedStateFromError == "function" || a !== null && typeof a.componentDidCatch == "function" && (vd === null || !vd.has(a)))) return n.flags |= 65536, i &= -i, n.lanes |= i, i = kc(i), Ac(i, e, n, r), yo(n, i), !1;
					break;
				case 22: if (n.memoizedState !== null) return n.flags |= 65536, !1;
			}
			n = n.return;
		} while (n !== null);
		return !1;
	}
	var Mc = Error(s(461)), Nc = !1;
	function Pc(e, t, n, r) {
		t.child = e === null ? fo(t, null, n, r) : uo(t, e.child, n, r);
	}
	function Fc(e, t, n, r, i) {
		n = n.render;
		var a = t.ref;
		if ("ref" in r) {
			var o = {};
			for (var s in r) s !== "ref" && (o[s] = r[s]);
		} else o = r;
		return Ca(t), r = Qo(e, t, n, o, a, i), s = ns(), e !== null && !Nc ? (rs(e, t, i), ll(e, t, i)) : (V && s && ea(t), t.flags |= 1, Pc(e, t, r, i), t.child);
	}
	function Ic(e, t, n, r, i) {
		if (e === null) {
			var a = n.type;
			return typeof a == "function" && !Ni(a) && a.defaultProps === void 0 && n.compare === null ? (t.tag = 15, t.type = a, Lc(e, t, a, r, i)) : (e = Ii(n.type, null, r, t, t.mode, i), e.ref = t.ref, e.return = t, t.child = e);
		}
		if (a = e.child, !ul(e, i)) {
			var o = a.memoizedProps;
			if (n = n.compare, n = n === null ? Hr : n, n(o, r) && e.ref === t.ref) return ll(e, t, i);
		}
		return t.flags |= 1, e = Pi(a, r), e.ref = t.ref, e.return = t, t.child = e;
	}
	function Lc(e, t, n, r, i) {
		if (e !== null) {
			var a = e.memoizedProps;
			if (Hr(a, r) && e.ref === t.ref) {
				if (Nc = !1, t.pendingProps = r = a, ul(e, i)) e.flags & 131072 && (Nc = !0);
				else return t.lanes = e.lanes, ll(e, t, i);
			}
		}
		return Gc(e, t, n, r, i);
	}
	function Rc(e, t, n, r) {
		var i = r.children, a = e === null ? null : e.memoizedState;
		if (e === null && t.stateNode === null && (t.stateNode = {
			_visibility: 1,
			_pendingMarkers: null,
			_retryCache: null,
			_transitions: null
		}), r.mode === "hidden") {
			if (t.flags & 128) {
				if (a = a === null ? n : a.baseLanes | n, e !== null) {
					for (r = t.child = e.child, i = 0; r !== null;) i = i | r.lanes | r.childLanes, r = r.sibling;
					r = i & ~a;
				} else r = 0, t.child = null;
				return Bc(e, t, a, n, r);
			}
			if (n & 536870912) t.memoizedState = {
				baseLanes: 0,
				cachePool: null
			}, e !== null && Ka(t, a === null ? null : a.cachePool), a === null ? Oo() : Do(t, a), Po(t);
			else return r = t.lanes = 536870912, Bc(e, t, a === null ? n : a.baseLanes | n, n, r);
		} else a === null ? (e !== null && Ka(t, null), Oo(), Fo()) : (Ka(t, a.cachePool), Do(t, a), Fo(), t.memoizedState = null);
		return Pc(e, t, i, n), t.child;
	}
	function zc(e, t) {
		return e !== null && e.tag === 22 || t.stateNode !== null || (t.stateNode = {
			_visibility: 1,
			_pendingMarkers: null,
			_retryCache: null,
			_transitions: null
		}), t.sibling;
	}
	function Bc(e, t, n, r, i) {
		var a = Ga();
		return a = a === null ? null : {
			parent: Aa._currentValue,
			pool: a
		}, t.memoizedState = {
			baseLanes: n,
			cachePool: a
		}, e !== null && Ka(t, null), Oo(), Po(t), e !== null && xa(e, t, r, !0), t.childLanes = i, null;
	}
	function Vc(e, t) {
		return t = el({
			mode: t.mode,
			children: t.children
		}, e.mode), t.ref = e.ref, e.child = t, t.return = e, t;
	}
	function Hc(e, t, n) {
		return uo(t, e.child, null, n), e = Vc(t, t.pendingProps), e.flags |= 2, Io(t), t.memoizedState = null, e;
	}
	function Uc(e, t, n) {
		var r = t.pendingProps, i = !!(t.flags & 128);
		if (t.flags &= -129, e === null) {
			if (V) {
				if (r.mode === "hidden") return e = Vc(t, r), t.lanes = 536870912, e.memoizedState = {
					baseLanes: 0,
					cachePool: null
				}, zc(null, e);
				if (No(t), (e = B) ? (e = am(e, aa), e = e !== null && e.data === "&" ? e : null, e !== null && (t.memoizedState = {
					dehydrated: e,
					treeContext: Yi === null ? null : {
						id: Xi,
						overflow: Zi
					},
					retryLane: 536870912,
					hydrationErrors: null
				}, n = zi(e), n.return = t, t.child = n, ra = t, B = null)) : e = null, e === null) throw sa(t);
				return t.lanes = 536870912, null;
			}
			return Vc(t, r);
		}
		var a = e.memoizedState;
		if (a !== null) {
			var o = a.dehydrated;
			if (No(t), i) {
				if (t.flags & 256) t.flags &= -257, t = Hc(e, t, n);
				else if (t.memoizedState !== null) t.child = e.child, t.flags |= 128, t = null;
				else throw Error(s(558));
			} else if (Nc || xa(e, t, n, !1), i = (n & e.childLanes) !== 0, Nc || i) {
				if (To.current === null) {
					if (r = q, r !== null && (o = bt(r, n), o !== 0 && o !== a.retryLane)) throw a.retryLane = o, Di(e, o), Pd(r, e, o), Mc;
					Kd();
				}
				t = Hc(e, t, n);
			} else e = a.treeContext, B = lm(o.nextSibling), ra = t, V = !0, ia = null, aa = !1, e !== null && na(t, e), t = Vc(t, r), t.flags |= 134221824;
			return t;
		}
		return e = Pi(e.child, {
			mode: r.mode,
			children: r.children
		}), e.ref = t.ref, t.child = e, e.return = t, e;
	}
	function Wc(e, t) {
		var n = t.ref;
		if (n === null) e !== null && e.ref !== null && (t.flags |= 4194816);
		else {
			if (typeof n != "function" && typeof n != "object") throw Error(s(284));
			(e === null || e.ref !== n) && (t.flags |= 4194816);
		}
	}
	function Gc(e, t, n, r, i) {
		return Ca(t), n = Qo(e, t, n, r, void 0, i), r = ns(), e !== null && !Nc ? (rs(e, t, i), ll(e, t, i)) : (V && r && ea(t), t.flags |= 1, Pc(e, t, n, i), t.child);
	}
	function Kc(e, t, n, r, i, a) {
		return Ca(t), t.updateQueue = null, n = es(t, r, n, i), $o(e), r = ns(), e !== null && !Nc ? (rs(e, t, a), ll(e, t, a)) : (V && r && ea(t), t.flags |= 1, Pc(e, t, n, a), t.child);
	}
	function qc(e, t, n, r, i) {
		if (Ca(t), t.stateNode === null) {
			var a = Ai, o = n.contextType;
			typeof o == "object" && o && (a = wa(o)), a = new n(r, a), t.memoizedState = a.state !== null && a.state !== void 0 ? a.state : null, a.updater = yc, t.stateNode = a, a._reactInternals = t, a = t.stateNode, a.props = r, a.state = t.memoizedState, a.refs = {}, mo(t), o = n.contextType, a.context = typeof o == "object" && o ? wa(o) : Ai, a.state = t.memoizedState, o = n.getDerivedStateFromProps, typeof o == "function" && (vc(t, n, o, r), a.state = t.memoizedState), typeof n.getDerivedStateFromProps == "function" || typeof a.getSnapshotBeforeUpdate == "function" || typeof a.UNSAFE_componentWillMount != "function" && typeof a.componentWillMount != "function" || (o = a.state, typeof a.componentWillMount == "function" && a.componentWillMount(), typeof a.UNSAFE_componentWillMount == "function" && a.UNSAFE_componentWillMount(), o !== a.state && yc.enqueueReplaceState(a, a.state, null), So(t, r, a, i), xo(), a.state = t.memoizedState), typeof a.componentDidMount == "function" && (t.flags |= 4194308), r = !0;
		} else if (e === null) {
			a = t.stateNode;
			var s = t.memoizedProps, c = Sc(n, s);
			a.props = c;
			var l = a.context, u = n.contextType;
			o = Ai, typeof u == "object" && u && (o = wa(u));
			var d = n.getDerivedStateFromProps;
			u = typeof d == "function" || typeof a.getSnapshotBeforeUpdate == "function", s = t.pendingProps !== s, u || typeof a.UNSAFE_componentWillReceiveProps != "function" && typeof a.componentWillReceiveProps != "function" || (s || l !== o) && xc(t, a, r, o), po = !1;
			var f = t.memoizedState;
			a.state = f, So(t, r, a, i), xo(), l = t.memoizedState, s || f !== l || po ? (typeof d == "function" && (vc(t, n, d, r), l = t.memoizedState), (c = po || bc(t, n, c, r, f, l, o)) ? (u || typeof a.UNSAFE_componentWillMount != "function" && typeof a.componentWillMount != "function" || (typeof a.componentWillMount == "function" && a.componentWillMount(), typeof a.UNSAFE_componentWillMount == "function" && a.UNSAFE_componentWillMount()), typeof a.componentDidMount == "function" && (t.flags |= 4194308)) : (typeof a.componentDidMount == "function" && (t.flags |= 4194308), t.memoizedProps = r, t.memoizedState = l), a.props = r, a.state = l, a.context = o, r = c) : (typeof a.componentDidMount == "function" && (t.flags |= 4194308), r = !1);
		} else {
			a = t.stateNode, ho(e, t), o = t.memoizedProps, u = Sc(n, o), a.props = u, d = t.pendingProps, f = a.context, l = n.contextType, c = Ai, typeof l == "object" && l && (c = wa(l)), s = n.getDerivedStateFromProps, (l = typeof s == "function" || typeof a.getSnapshotBeforeUpdate == "function") || typeof a.UNSAFE_componentWillReceiveProps != "function" && typeof a.componentWillReceiveProps != "function" || (o !== d || f !== c) && xc(t, a, r, c), po = !1, f = t.memoizedState, a.state = f, So(t, r, a, i), xo();
			var p = t.memoizedState;
			o !== d || f !== p || po || e !== null && e.dependencies !== null && Sa(e.dependencies) ? (typeof s == "function" && (vc(t, n, s, r), p = t.memoizedState), (u = po || bc(t, n, u, r, f, p, c) || e !== null && e.dependencies !== null && Sa(e.dependencies)) ? (l || typeof a.UNSAFE_componentWillUpdate != "function" && typeof a.componentWillUpdate != "function" || (typeof a.componentWillUpdate == "function" && a.componentWillUpdate(r, p, c), typeof a.UNSAFE_componentWillUpdate == "function" && a.UNSAFE_componentWillUpdate(r, p, c)), typeof a.componentDidUpdate == "function" && (t.flags |= 4), typeof a.getSnapshotBeforeUpdate == "function" && (t.flags |= 1024)) : (typeof a.componentDidUpdate != "function" || o === e.memoizedProps && f === e.memoizedState || (t.flags |= 4), typeof a.getSnapshotBeforeUpdate != "function" || o === e.memoizedProps && f === e.memoizedState || (t.flags |= 1024), t.memoizedProps = r, t.memoizedState = p), a.props = r, a.state = p, a.context = c, r = u) : (typeof a.componentDidUpdate != "function" || o === e.memoizedProps && f === e.memoizedState || (t.flags |= 4), typeof a.getSnapshotBeforeUpdate != "function" || o === e.memoizedProps && f === e.memoizedState || (t.flags |= 1024), r = !1);
		}
		return a = r, Wc(e, t), r = !!(t.flags & 128), a || r ? (a = t.stateNode, n = r && typeof n.getDerivedStateFromError != "function" ? null : a.render(), t.flags |= 1, e !== null && r ? (t.child = uo(t, e.child, null, i), t.child = uo(t, null, n, i)) : Pc(e, t, n, i), t.memoizedState = a.state, e = t.child) : e = ll(e, t, i), e;
	}
	function Jc(e, t, n, r) {
		return da(), t.flags |= 256, Pc(e, t, n, r), t.child;
	}
	var Yc = {
		dehydrated: null,
		treeContext: null,
		retryLane: 0,
		hydrationErrors: null
	};
	function Xc(e) {
		return {
			baseLanes: e,
			cachePool: qa()
		};
	}
	function Zc(e, t, n) {
		return e = e === null ? 0 : e.childLanes & ~n, t && (e |= ld), e;
	}
	function Qc(e, t, n) {
		var r = t.pendingProps, i = !1, a = !!(t.flags & 128), o;
		if ((o = a) || (o = e !== null && e.memoizedState === null ? !1 : !!(Lo.current & 2)), o && (i = !0, t.flags &= -129), o = !!(t.flags & 32), t.flags &= -33, e === null) {
			if (V) {
				if (i ? Mo(t) : Fo(), (e = B) ? (e = am(e, aa), e = e !== null && e.data !== "&" ? e : null, e !== null && (t.memoizedState = {
					dehydrated: e,
					treeContext: Yi === null ? null : {
						id: Xi,
						overflow: Zi
					},
					retryLane: 536870912,
					hydrationErrors: null
				}, n = zi(e), n.return = t, t.child = n, ra = t, B = null)) : e = null, e === null) throw sa(t);
				return t.lanes = sm(e) ? 32 : 536870912, null;
			}
			return a = r.children, r = r.fallback, i ? (Fo(), i = t.mode, a = el({
				mode: "hidden",
				children: a
			}, i), r = Li(r, i, n, null), a.return = t, r.return = t, a.sibling = r, t.child = a, r = t.child, r.memoizedState = Xc(n), r.childLanes = Zc(e, o, n), t.memoizedState = Yc, zc(null, r)) : (Mo(t), $c(t, a));
		}
		var s = e.memoizedState;
		if (s !== null) {
			var c = s.dehydrated;
			if (c !== null) return nl(e, t, a, o, r, c, s, n);
		}
		return i ? (Fo(), i = r.fallback, a = t.mode, s = e.child, c = s.sibling, r = Pi(s, {
			mode: "hidden",
			children: r.children
		}), r.subtreeFlags = s.subtreeFlags & 1206910976, c === null ? (i = Li(i, a, n, null), i.flags |= 2) : i = Pi(c, i), i.return = t, r.return = t, r.sibling = i, t.child = r, zc(null, r), r = t.child, i = e.child.memoizedState, i === null ? i = Xc(n) : (a = i.cachePool, a === null ? a = qa() : (s = Aa._currentValue, a = a.parent === s ? a : {
			parent: s,
			pool: s
		}), i = {
			baseLanes: i.baseLanes | n,
			cachePool: a
		}), r.memoizedState = i, r.childLanes = Zc(e, o, n), t.memoizedState = Yc, zc(e.child, r)) : (Mo(t), n = e.child, e = n.sibling, n = Pi(n, {
			mode: "visible",
			children: r.children
		}), n.return = t, n.sibling = null, e !== null && (o = t.deletions, o === null ? (t.deletions = [e], t.flags |= 16) : o.push(e)), t.child = n, t.memoizedState = null, n);
	}
	function $c(e, t) {
		return t = el({
			mode: "visible",
			children: t
		}, e.mode), t.return = e, e.child = t;
	}
	function el(e, t) {
		return e = Mi(22, e, null, t), e.lanes = 0, e;
	}
	function tl(e, t, n) {
		return uo(t, e.child, null, n), e = $c(t, t.pendingProps.children), e.flags |= 2, t.memoizedState = null, e;
	}
	function nl(e, t, n, r, i, a, o, c) {
		if (n) return t.flags & 256 ? (Mo(t), t.flags &= -257, tl(e, t, c)) : t.memoizedState === null ? (Fo(), a = i.fallback, o = t.mode, i = el({
			mode: "visible",
			children: i.children
		}, o), a = Li(a, o, c, null), a.flags |= 2, i.return = t, a.return = t, i.sibling = a, t.child = i, uo(t, e.child, null, c), i = t.child, i.memoizedState = Xc(c), i.childLanes = Zc(e, r, c), t.memoizedState = Yc, zc(null, i)) : (Fo(), t.child = e.child, t.flags |= 128, null);
		if (Mo(t), sm(a)) {
			if (r = a.nextSibling && a.nextSibling.dataset, r) var l = r.dgst;
			return r = l, r !== "" && (i = Error(s(419)), i.stack = "", i.digest = r, pa({
				value: i,
				source: null,
				stack: null
			})), tl(e, t, c);
		}
		if (Nc || xa(e, t, c, !1), r = (c & e.childLanes) !== 0, Nc || r) {
			if (To.current !== null) return tl(e, t, c);
			if (r = q, r !== null && (i = bt(r, c), i !== 0 && i !== o.retryLane)) throw o.retryLane = i, Di(e, i), Pd(r, e, i), Mc;
			return om(a) || Kd(), tl(e, t, c);
		}
		return om(a) ? (t.flags |= 192, t.child = e.child, null) : (e = o.treeContext, B = lm(a.nextSibling), ra = t, V = !0, ia = null, aa = !1, e !== null && na(t, e), t = $c(t, i.children), t.flags |= 134221824, t);
	}
	function rl(e, t, n) {
		e.lanes |= t;
		var r = e.alternate;
		r !== null && (r.lanes |= t), ya(e.return, t, n);
	}
	function il(e) {
		for (var t = null; e !== null;) {
			var n = e.alternate;
			n !== null && Bo(n) === null && (t = e), e = e.sibling;
		}
		return t;
	}
	function al(e, t, n, r, i, a) {
		var o = e.memoizedState;
		o === null ? e.memoizedState = {
			isBackwards: t,
			rendering: null,
			renderingStartTime: 0,
			last: r,
			tail: n,
			tailMode: i,
			treeForkCount: a
		} : (o.isBackwards = t, o.rendering = null, o.renderingStartTime = 0, o.last = r, o.tail = n, o.tailMode = i, o.treeForkCount = a);
	}
	function ol(e) {
		var t = e.child;
		for (e.child = null; t !== null;) {
			var n = t.sibling;
			t.sibling = e.child, e.child = t, t = n;
		}
	}
	function sl(e, t, n) {
		var r = t.pendingProps, i = r.revealOrder, a = r.tail;
		r = r.children;
		var o = Lo.current;
		if (t.flags & 128) return Ro(t, o), null;
		var s = !!(o & 2);
		if (s ? (o = o & 1 | 2, t.flags |= 128) : o &= 1, Ro(t, o), i === "backwards" && e !== null ? (ol(e), Pc(e, t, r, n), ol(e)) : Pc(e, t, r, n), r = V ? Ki : 0, !s && e !== null && e.flags & 128) a: for (e = t.child; e !== null;) {
			if (e.tag === 13) e.memoizedState !== null && rl(e, n, t);
			else if (e.tag === 19) rl(e, n, t);
			else if (e.child !== null) {
				e.child.return = e, e = e.child;
				continue;
			}
			if (e === t) break a;
			for (; e.sibling === null;) {
				if (e.return === null || e.return === t) break a;
				e = e.return;
			}
			e.sibling.return = e.return, e = e.sibling;
		}
		switch (i) {
			case "backwards":
				n = il(t.child), n === null ? (i = t.child, t.child = null) : (i = n.sibling, n.sibling = null, ol(t)), al(t, !0, i, null, a, r);
				break;
			case "unstable_legacy-backwards":
				for (n = null, i = t.child, t.child = null; i !== null;) {
					if (e = i.alternate, e !== null && Bo(e) === null) {
						t.child = i;
						break;
					}
					e = i.sibling, i.sibling = n, n = i, i = e;
				}
				al(t, !0, n, null, a, r);
				break;
			case "together":
				al(t, !1, null, null, void 0, r);
				break;
			case "independent":
				t.memoizedState = null;
				break;
			default: n = il(t.child), n === null ? (i = t.child, t.child = null) : (i = n.sibling, n.sibling = null), al(t, !1, i, n, a, r);
		}
		return t.child;
	}
	function cl(e, t, n) {
		var r = t.pendingProps;
		return _a(t, t.type, r.value), Pc(e, t, r.children, n), t.child;
	}
	function ll(e, t, n) {
		if (e !== null && (t.dependencies = e.dependencies), od |= t.lanes, (n & t.childLanes) === 0) {
			if (e !== null) {
				if (xa(e, t, n, !1), (n & t.childLanes) === 0) return null;
			} else return null;
		}
		if (e !== null && t.child !== e.child) throw Error(s(153));
		if (t.child !== null) {
			for (e = t.child, n = Pi(e, e.pendingProps), t.child = n, n.return = t; e.sibling !== null;) e = e.sibling, n = n.sibling = Pi(e, e.pendingProps), n.return = t;
			n.sibling = null;
		}
		return t.child;
	}
	function ul(e, t) {
		return (e.lanes & t) !== 0 || (e = e.dependencies, !!(e !== null && Sa(e)));
	}
	function dl(e, t, n) {
		switch (t.tag) {
			case 3:
				je(t, t.stateNode.containerInfo), _a(t, Aa, e.memoizedState.cache), da();
				break;
			case 27:
			case 5:
				Ne(t);
				break;
			case 4:
				je(t, t.stateNode.containerInfo);
				break;
			case 10:
				_a(t, t.type, t.memoizedProps.value);
				break;
			case 31:
				if (t.memoizedState !== null) return t.flags |= 128, No(t), null;
				break;
			case 13:
				var r = t.memoizedState;
				if (r !== null) {
					if (r.dehydrated !== null) return Mo(t), t.flags |= 128, null;
					r = xa(e, t, n, !1);
					var i = t.child.childLanes;
					return r || (n & i) !== 0 ? Qc(e, t, n) : (Mo(t), e = ll(e, t, n), e === null ? null : e.sibling);
				}
				Mo(t);
				break;
			case 19:
				if (t.flags & 128) return sl(e, t, n);
				if (i = !!(e.flags & 128), r = (n & t.childLanes) !== 0, r ||= (xa(e, t, n, !1), (n & t.childLanes) !== 0), i) {
					if (r) return sl(e, t, n);
					t.flags |= 128;
				}
				if (i = t.memoizedState, i !== null && (i.rendering = null, i.tail = null, i.lastEffect = null), Ro(t, Lo.current), r) break;
				return null;
			case 22: return t.lanes = 0, Rc(e, t, n, t.pendingProps);
			case 24: _a(t, Aa, e.memoizedState.cache);
		}
		return ll(e, t, n);
	}
	function fl(e, t, n) {
		if (e !== null) {
			if (e.memoizedProps !== t.pendingProps) Nc = !0;
			else {
				if (!ul(e, n) && !(t.flags & 128)) return Nc = !1, dl(e, t, n);
				Nc = !!(e.flags & 131072);
			}
		} else Nc = !1, V && t.flags & 1048576 && $i(t, Ki, t.index);
		switch (t.lanes = 0, t.tag) {
			case 16:
				a: {
					var r = t.pendingProps;
					if (e = eo(t.elementType), t.type = e, typeof e == "function") Ni(e) ? (r = Sc(e, r), t.tag = 1, t = qc(null, t, e, r, n)) : (t.tag = 0, t = Gc(null, t, e, r, n));
					else {
						if (e != null) {
							var i = e.$$typeof;
							if (i === ce) {
								t.tag = 11, t = Fc(null, t, e, r, n);
								break a;
							}
							if (i === ue) {
								t.tag = 14, t = Ic(null, t, e, r, n);
								break a;
							}
							if (i === D) {
								t.tag = 10, t.type = e, t = cl(null, t, n);
								break a;
							}
						}
						throw t = be(e) || e, Error(s(306, t, ""));
					}
				}
				return t;
			case 0: return Gc(e, t, t.type, t.pendingProps, n);
			case 1: return r = t.type, i = Sc(r, t.pendingProps), qc(e, t, r, i, n);
			case 3:
				a: {
					if (je(t, t.stateNode.containerInfo), e === null) throw Error(s(387));
					r = t.pendingProps;
					var a = t.memoizedState;
					i = a.element, ho(e, t), So(t, r, null, n);
					var o = t.memoizedState;
					if (r = o.cache, _a(t, Aa, r), r !== a.cache && ba(t, [Aa], n, !0), xo(), r = o.element, a.isDehydrated) {
						if (a = {
							element: r,
							isDehydrated: !1,
							cache: o.cache
						}, t.updateQueue.baseState = a, t.memoizedState = a, t.flags & 256) {
							t = Jc(e, t, r, n);
							break a;
						}
						if (r !== i) {
							i = Hi(Error(s(424)), t), pa(i), t = Jc(e, t, r, n);
							break a;
						}
						switch (e = t.stateNode.containerInfo, e.nodeType) {
							case 9:
								e = e.body;
								break;
							default: e = e.nodeName === "HTML" ? e.ownerDocument.body : e;
						}
						for (B = lm(e.firstChild), ra = t, V = !0, ia = null, aa = !0, n = fo(t, null, r, n), t.child = n; n;) n.flags = n.flags & -3 | 134221824, n = n.sibling;
					} else {
						if (da(), r === i) {
							t = ll(e, t, n);
							break a;
						}
						Pc(e, t, r, n);
					}
					t = t.child;
				}
				return t;
			case 26: return Wc(e, t), e === null ? (n = Nm(t.type, null, t.pendingProps, null)) ? t.memoizedState = n : V || (t.stateNode = fp(t.type, t.pendingProps, ke.current, t)) : t.memoizedState = Nm(t.type, e.memoizedProps, t.pendingProps, e.memoizedState), null;
			case 27: return Ne(t), e === null && V && (r = t.stateNode = hm(t.type, t.pendingProps, ke.current), ra = t, aa = !0, i = B, Sp(t.type) ? (um = i, B = lm(r.firstChild)) : B = i), Pc(e, t, t.pendingProps.children, n), Wc(e, t), e === null && (t.flags |= 4194304), t.child;
			case 5: return e === null && V && ((i = r = B) && (r = rm(r, t.type, t.pendingProps, aa), r === null ? i = !1 : (t.stateNode = r, ra = t, B = lm(r.firstChild), aa = !1, i = !0)), i || sa(t)), Ne(t), i = t.type, a = t.pendingProps, o = e === null ? null : e.memoizedProps, r = a.children, pp(i, a) ? r = null : o !== null && pp(i, o) && (t.flags |= 32), t.memoizedState !== null && (i = Qo(e, t, ts, null, null, n), sh._currentValue = i), Wc(e, t), Pc(e, t, r, n), t.child;
			case 6: return e === null && V && ((e = n = B) && (n = im(n, t.pendingProps, aa), n === null ? e = !1 : (t.stateNode = n, ra = t, B = null, e = !0)), e || sa(t)), null;
			case 13: return Qc(e, t, n);
			case 4: return je(t, t.stateNode.containerInfo), r = t.pendingProps, e === null ? t.child = uo(t, null, r, n) : Pc(e, t, r, n), t.child;
			case 11: return Fc(e, t, t.type, t.pendingProps, n);
			case 7: return r = t.pendingProps, Wc(e, t), Pc(e, t, r, n), t.child;
			case 8: return Pc(e, t, t.pendingProps.children, n), t.child;
			case 12: return Pc(e, t, t.pendingProps.children, n), t.child;
			case 10: return cl(e, t, n);
			case 9: return i = t.type._context, r = t.pendingProps.children, Ca(t), i = wa(i), r = r(i), t.flags |= 1, Pc(e, t, r, n), t.child;
			case 14: return Ic(e, t, t.type, t.pendingProps, n);
			case 15: return Lc(e, t, t.type, t.pendingProps, n);
			case 19: return sl(e, t, n);
			case 31: return Uc(e, t, n);
			case 22: return Rc(e, t, n, t.pendingProps);
			case 24: return Ca(t), r = wa(Aa), e === null ? (i = Ga(), i === null && (i = q, a = ja(), i.pooledCache = a, a.refCount++, a !== null && (i.pooledCacheLanes |= n), i = a), t.memoizedState = {
				parent: r,
				cache: i
			}, mo(t), _a(t, Aa, i)) : ((e.lanes & n) !== 0 && (ho(e, t), So(t, null, null, n), xo()), i = e.memoizedState, a = t.memoizedState, i.parent === r ? (r = a.cache, _a(t, Aa, r), r !== i.cache && ba(t, [Aa], n, !0)) : (i = {
				parent: r,
				cache: r
			}, t.memoizedState = i, t.lanes === 0 && (t.memoizedState = t.updateQueue.baseState = i), _a(t, Aa, r))), Pc(e, t, t.pendingProps.children, n), t.child;
			case 30: return t.stateNode === null && (t.stateNode = {
				autoName: null,
				paired: null,
				clones: null,
				ref: null
			}), r = t.pendingProps, r.name != null && r.name !== "auto" ? t.flags |= e === null ? 18882560 : 18874368 : V && ea(t), e !== null && e.memoizedProps.name !== r.name ? t.flags |= 4194816 : Wc(e, t), Pc(e, t, r.children, n), t.child;
			case 29: throw t.pendingProps;
		}
		throw Error(s(156, t.tag));
	}
	function pl(e) {
		e.flags |= 4;
	}
	function ml(e, t, n, r, i) {
		var a;
		if ((a = !!(e.mode & 32)) && (a = n === null ? Jm(t, r) : Jm(t, r) && (r.src !== n.src || r.srcSet !== n.srcSet)), a) {
			if (e.flags |= 16777216, (i & 335544128) === i) {
				if (e.stateNode.complete) e.flags |= 8192;
				else if (Ud()) e.flags |= 8192;
				else throw to = Za, Ya;
			}
		} else e.flags &= -16777217;
	}
	function hl(e, t) {
		if (t.type !== "stylesheet" || t.state.loading & 4) e.flags &= -16777217;
		else if (e.flags |= 16777216, !Ym(t)) {
			if (Ud()) e.flags |= 8192;
			else throw to = Za, Ya;
		}
	}
	function gl(e, t) {
		t !== null && (e.flags |= 4), e.flags & 16384 && (t = e.tag === 22 ? 536870912 : mt(), e.lanes |= t, ud |= t);
	}
	function _l(e, t) {
		if (!V) switch (e.tailMode) {
			case "visible": break;
			case "collapsed":
				for (var n = e.tail, r = null; n !== null;) n.alternate !== null && (r = n), n = n.sibling;
				r === null ? t || e.tail === null ? e.tail = null : e.tail.sibling = null : r.sibling = null;
				break;
			default:
				for (t = e.tail, n = null; t !== null;) t.alternate !== null && (n = t), t = t.sibling;
				n === null ? e.tail = null : n.sibling = null;
		}
	}
	function W(e) {
		var t = e.alternate !== null && e.alternate.child === e.child, n = 0, r = 0;
		if (t) for (var i = e.child; i !== null;) n |= i.lanes | i.childLanes, r |= i.subtreeFlags & 1206910976, r |= i.flags & 1206910976, i.return = e, i = i.sibling;
		else for (i = e.child; i !== null;) n |= i.lanes | i.childLanes, r |= i.subtreeFlags, r |= i.flags, i.return = e, i = i.sibling;
		return e.subtreeFlags |= r, e.childLanes = n, t;
	}
	function vl(e, t, n) {
		var r = t.pendingProps;
		switch (ta(t), t.tag) {
			case 16:
			case 15:
			case 0:
			case 11:
			case 7:
			case 8:
			case 12:
			case 9:
			case 14: return W(t), null;
			case 1: return W(t), null;
			case 3: return n = t.stateNode, r = null, e !== null && (r = e.memoizedState.cache), t.memoizedState.cache !== r && (t.flags |= 2048), va(Aa), Me(), n.pendingContext && (n.context = n.pendingContext, n.pendingContext = null), (e === null || e.child === null) && (ua(t) ? pl(t) : e === null || e.memoizedState.isDehydrated && !(t.flags & 256) || (t.flags |= 1024, fa())), W(t), null;
			case 26:
				var i = t.type, a = t.memoizedState;
				return e === null ? (pl(t), a === null ? (W(t), ml(t, i, null, r, n)) : (W(t), hl(t, a))) : a ? a === e.memoizedState ? (W(t), t.flags &= -16777217) : (pl(t), W(t), hl(t, a)) : (e = e.memoizedProps, e !== r && pl(t), W(t), ml(t, i, e, r, n)), null;
			case 27:
				if (Pe(t), n = ke.current, i = t.type, e !== null && t.stateNode != null) e.memoizedProps !== r && pl(t);
				else {
					if (!r) {
						if (t.stateNode === null) throw Error(s(166));
						return W(t), t.subtreeFlags &= -33554433, null;
					}
					e = De.current, ua(t) ? ca(t, e) : (e = hm(i, r, n), t.stateNode = e, pl(t));
				}
				return W(t), t.subtreeFlags &= -33554433, null;
			case 5:
				if (Pe(t), i = t.type, e !== null && t.stateNode != null) e.memoizedProps !== r && pl(t);
				else {
					if (!r) {
						if (t.stateNode === null) throw Error(s(166));
						return W(t), t.subtreeFlags &= -33554433, null;
					}
					if (a = De.current, ua(t)) ca(t, a);
					else {
						var o = lp(ke.current);
						switch (a) {
							case 1:
								a = o.createElementNS("http://www.w3.org/2000/svg", i);
								break;
							case 2:
								a = o.createElementNS("http://www.w3.org/1998/Math/MathML", i);
								break;
							default: switch (i) {
								case "svg":
									a = o.createElementNS("http://www.w3.org/2000/svg", i);
									break;
								case "math":
									a = o.createElementNS("http://www.w3.org/1998/Math/MathML", i);
									break;
								case "script":
									a = o.createElement("div"), a.innerHTML = "<script><\/script>", a = a.removeChild(a.firstChild);
									break;
								case "select":
									a = typeof r.is == "string" ? o.createElement("select", { is: r.is }) : o.createElement("select"), r.multiple ? a.multiple = !0 : r.size && (a.size = r.size);
									break;
								default: a = typeof r.is == "string" ? o.createElement(i, { is: r.is }) : o.createElement(i);
							}
						}
						a[F] = t, a[Et] = r;
						a: for (o = t.child; o !== null;) {
							if (o.tag === 5 || o.tag === 6) a.appendChild(o.stateNode);
							else if (o.tag !== 4 && o.tag !== 27 && o.child !== null) {
								o.child.return = o, o = o.child;
								continue;
							}
							if (o === t) break a;
							for (; o.sibling === null;) {
								if (o.return === null || o.return === t) break a;
								o = o.return;
							}
							o.sibling.return = o.return, o = o.sibling;
						}
						t.stateNode = a;
						a: switch (np(a, i, r), i) {
							case "button":
							case "input":
							case "select":
							case "textarea":
								r = !!r.autoFocus;
								break a;
							case "img":
								r = !0;
								break a;
							default: r = !1;
						}
						r && pl(t);
					}
				}
				return W(t), t.subtreeFlags &= -33554433, ml(t, t.type, e === null ? null : e.memoizedProps, t.pendingProps, n), null;
			case 6:
				if (e && t.stateNode != null) e.memoizedProps !== r && pl(t);
				else {
					if (typeof r != "string" && t.stateNode === null) throw Error(s(166));
					if (e = ke.current, ua(t)) {
						if (e = t.stateNode, n = t.memoizedProps, r = null, i = ra, i !== null) switch (i.tag) {
							case 27:
							case 5: r = i.memoizedProps;
						}
						e[F] = t, e = !!(e.nodeValue === n || r !== null && !0 === r.suppressHydrationWarning || ep(e.nodeValue, n)), e || sa(t, !0);
					} else e = lp(e).createTextNode(r), e[F] = t, t.stateNode = e;
				}
				return W(t), null;
			case 31:
				if (n = t.memoizedState, e === null || e.memoizedState !== null) {
					if (r = ua(t), n !== null) {
						if (e === null) {
							if (!r) throw Error(s(318));
							if (e = t.memoizedState, e = e === null ? null : e.dehydrated, !e) throw Error(s(557));
							e[F] = t;
						} else da(), !(t.flags & 128) && (t.memoizedState = null), t.flags |= 4;
						W(t), e = !1;
					} else n = fa(), e !== null && e.memoizedState !== null && (e.memoizedState.hydrationErrors = n), e = !0;
					if (!e) return t.flags & 256 ? (Io(t), t) : (Io(t), null);
					if (t.flags & 128) throw Error(s(558));
				}
				return W(t), null;
			case 13:
				if (r = t.memoizedState, e === null || e.memoizedState !== null && e.memoizedState.dehydrated !== null) {
					if (i = ua(t), r !== null && r.dehydrated !== null) {
						if (e === null) {
							if (!i) throw Error(s(318));
							if (i = t.memoizedState, i = i === null ? null : i.dehydrated, !i) throw Error(s(317));
							i[F] = t;
						} else da(), !(t.flags & 128) && (t.memoizedState = null), t.flags |= 4;
						W(t), i = !1;
					} else i = fa(), e !== null && e.memoizedState !== null && (e.memoizedState.hydrationErrors = i), i = !0;
					if (!i) return t.flags & 256 ? (Io(t), t) : (Io(t), null);
				}
				return Io(t), t.flags & 128 ? (t.lanes = n, t) : (n = r !== null, e = e !== null && e.memoizedState !== null, n && (r = t.child, i = null, r.alternate !== null && r.alternate.memoizedState !== null && r.alternate.memoizedState.cachePool !== null && (i = r.alternate.memoizedState.cachePool.pool), a = null, r.memoizedState !== null && r.memoizedState.cachePool !== null && (a = r.memoizedState.cachePool.pool), a !== i && (r.flags |= 2048)), n !== e && n && (t.child.flags |= 8192), gl(t, t.updateQueue), W(t), null);
			case 4: return Me(), e === null && Wf(t.stateNode.containerInfo), t.flags |= 67108864, W(t), null;
			case 10: return va(t.type), W(t), null;
			case 19:
				if (zo(t), r = t.memoizedState, r === null) return W(t), null;
				if (i = !!(t.flags & 128), a = r.rendering, a === null) {
					if (i) _l(r, !1);
					else {
						if (ad !== 0 || e !== null && e.flags & 128) for (e = t.child; e !== null;) {
							if (a = Bo(e), a !== null) {
								for (t.flags |= 128, _l(r, !1), e = a.updateQueue, t.updateQueue = e, gl(t, e), t.subtreeFlags = 0, e = n, n = t.child; n !== null;) Fi(n, e), n = n.sibling;
								return Ro(t, Lo.current & 1 | 2), V && Qi(t, r.treeForkCount), t.child;
							}
							e = e.sibling;
						}
						r.tail !== null && Ge() > gd && (t.flags |= 128, i = !0, _l(r, !1), t.lanes = 4194304);
					}
				} else {
					if (!i) {
						if (e = Bo(a), e !== null) {
							if (t.flags |= 128, i = !0, e = e.updateQueue, t.updateQueue = e, gl(t, e), _l(r, !0), r.tail === null && r.tailMode !== "collapsed" && r.tailMode !== "visible" && !a.alternate && !V) return W(t), null;
						} else 2 * Ge() - r.renderingStartTime > gd && n !== 536870912 && (t.flags |= 128, i = !0, _l(r, !1), t.lanes = 4194304);
					}
					r.isBackwards ? (a.sibling = t.child, t.child = a) : (e = r.last, e === null ? t.child = a : e.sibling = a, r.last = a);
				}
				if (r.tail !== null) {
					e = r.tail;
					a: {
						for (n = e; n !== null;) {
							if (n.alternate !== null) {
								n = !1;
								break a;
							}
							n = n.sibling;
						}
						n = !0;
					}
					return r.rendering = e, r.tail = e.sibling, r.renderingStartTime = Ge(), e.sibling = null, a = Lo.current, a = i ? a & 1 | 2 : a & 1, r.tailMode === "visible" || r.tailMode === "collapsed" || !n || V ? Ro(t, a) : (n = a, j(Ao, t), j(Lo, n), jo === null && (jo = t)), V && Qi(t, r.treeForkCount), e;
				}
				return W(t), null;
			case 22:
			case 23: return Io(t), ko(), r = t.memoizedState !== null, e === null ? r && (t.flags |= 8192) : e.memoizedState !== null !== r && (t.flags |= 8192), r ? n & 536870912 && !(t.flags & 128) && (W(t), t.subtreeFlags & 6 && (t.flags |= 8192)) : W(t), n = t.updateQueue, n !== null && gl(t, n.retryQueue), n = null, e !== null && e.memoizedState !== null && e.memoizedState.cachePool !== null && (n = e.memoizedState.cachePool.pool), r = null, t.memoizedState !== null && t.memoizedState.cachePool !== null && (r = t.memoizedState.cachePool.pool), r !== n && (t.flags |= 2048), e !== null && Ee(Wa), null;
			case 24: return n = null, e !== null && (n = e.memoizedState.cache), t.memoizedState.cache !== n && (t.flags |= 2048), va(Aa), W(t), null;
			case 25: return null;
			case 30: return t.flags |= 33554432, W(t), null;
		}
		throw Error(s(156, t.tag));
	}
	function yl(e, t) {
		switch (ta(t), t.tag) {
			case 1: return e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
			case 3: return va(Aa), Me(), e = t.flags, e & 65536 && !(e & 128) ? (t.flags = e & -65537 | 128, t) : null;
			case 26:
			case 27:
			case 5: return Pe(t), null;
			case 31:
				if (t.memoizedState !== null) {
					if (Io(t), t.alternate === null) throw Error(s(340));
					da();
				}
				return e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
			case 13:
				if (Io(t), e = t.memoizedState, e !== null && e.dehydrated !== null) {
					if (t.alternate === null) throw Error(s(340));
					da();
				}
				return e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
			case 19: return zo(t), e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, e = t.memoizedState, e !== null && (e.rendering = null, e.tail = null), t.flags |= 4, t) : null;
			case 4: return Me(), null;
			case 10: return va(t.type), null;
			case 22:
			case 23: return Io(t), ko(), e !== null && Ee(Wa), e = t.flags, e & 65536 ? (t.flags = e & -65537 | 128, t) : null;
			case 24: return va(Aa), null;
			case 25: return null;
			default: return null;
		}
	}
	function bl(e, t) {
		switch (ta(t), t.tag) {
			case 3:
				va(Aa), Me();
				break;
			case 26:
			case 27:
			case 5:
				Pe(t);
				break;
			case 4:
				Me();
				break;
			case 31:
				t.memoizedState !== null && Io(t);
				break;
			case 13:
				Io(t);
				break;
			case 19:
				zo(t);
				break;
			case 10:
				va(t.type);
				break;
			case 22:
			case 23:
				Io(t), ko(), e !== null && Ee(Wa);
				break;
			case 24: va(Aa);
		}
	}
	function xl(e, t) {
		try {
			var n = t.updateQueue, r = n === null ? null : n.lastEffect;
			if (r !== null) {
				var i = r.next;
				n = i;
				do {
					if ((n.tag & e) === e) {
						r = void 0;
						var a = n.create, o = n.inst;
						r = a(), o.destroy = r;
					}
					n = n.next;
				} while (n !== i);
			}
		} catch (e) {
			Z(t, t.return, e);
		}
	}
	function Sl(e, t, n) {
		try {
			var r = t.updateQueue, i = r === null ? null : r.lastEffect;
			if (i !== null) {
				var a = i.next;
				r = a;
				do {
					if ((r.tag & e) === e) {
						var o = r.inst, s = o.destroy;
						if (s !== void 0) {
							o.destroy = void 0, i = t;
							var c = n, l = s;
							try {
								l();
							} catch (e) {
								Z(i, c, e);
							}
						}
					}
					r = r.next;
				} while (r !== a);
			}
		} catch (e) {
			Z(t, t.return, e);
		}
	}
	function Cl(e) {
		var t = e.updateQueue;
		if (t !== null) {
			var n = e.stateNode;
			try {
				wo(t, n);
			} catch (t) {
				Z(e, e.return, t);
			}
		}
	}
	function wl(e, t, n) {
		n.props = Sc(e.type, e.memoizedProps), n.state = e.memoizedState;
		try {
			n.componentWillUnmount();
		} catch (n) {
			Z(e, t, n);
		}
	}
	function Tl(e, t) {
		try {
			var n = e.ref;
			if (n !== null) {
				switch (e.tag) {
					case 26:
					case 27:
					case 5:
						var r = e.stateNode;
						break;
					case 30:
						var i = e.stateNode, a = _i(e.memoizedProps, i);
						(i.ref === null || i.ref.name !== a) && (i.ref = Pp(a)), r = i.ref;
						break;
					case 7:
						if (e.stateNode === null) {
							var o = new Fp(e);
							h(e.child, !1, Qp, o, void 0, void 0), e.stateNode = o;
						}
						r = e.stateNode;
						break;
					default: r = e.stateNode;
				}
				typeof n == "function" ? e.refCleanup = n(r) : n.current = r;
			}
		} catch (n) {
			Z(e, t, n);
		}
	}
	function El(e, t) {
		var n = e.ref, r = e.refCleanup;
		if (n !== null) {
			if (typeof r == "function") try {
				r();
			} catch (n) {
				Z(e, t, n);
			} finally {
				e.refCleanup = null, e = e.alternate, e != null && (e.refCleanup = null);
			}
			else if (typeof n == "function") try {
				n(null);
			} catch (n) {
				Z(e, t, n);
			}
			else n.current = null;
		}
	}
	function Dl(e, t) {
		if ((e.tag === 5 || e.tag === 27 || e.tag === 6) && e.alternate === null && t !== null) for (var n = 0; n < t.length; n++) em(e.stateNode, t[n]);
	}
	function Ol(e) {
		for (var t = e.return; t !== null && (jl(t) && em(e.stateNode, t.stateNode), !Al(t));) t = t.return;
	}
	function kl(e) {
		for (var t = e.return; t !== null && (jl(t) && tm(e.stateNode, t.stateNode), !Al(t));) t = t.return;
	}
	function Al(e) {
		return e.tag === 5 || e.tag === 3 || e.tag === 27;
	}
	function jl(e) {
		return e && e.tag === 7 && e.stateNode !== null;
	}
	function Ml(e) {
		var t = e.type, n = e.memoizedProps, r = e.stateNode;
		try {
			a: switch (t) {
				case "button":
				case "input":
				case "select":
				case "textarea":
					n.autoFocus && r.focus();
					break a;
				case "img": n.src ? r.src = n.src : n.srcSet && (r.srcset = n.srcSet);
			}
		} catch (t) {
			Z(e, e.return, t);
		}
	}
	function Nl(e, t, n) {
		try {
			var r = e.stateNode;
			ip(r, e.type, n, t), r[Et] = t;
		} catch (t) {
			Z(e, e.return, t);
		}
	}
	function Pl(e) {
		return e.tag === 5 || e.tag === 3 || e.tag === 26 || e.tag === 27 && Sp(e.type) || e.tag === 4;
	}
	function Fl(e) {
		a: for (;;) {
			for (; e.sibling === null;) {
				if (e.return === null || Pl(e.return)) return null;
				e = e.return;
			}
			for (e.sibling.return = e.return, e = e.sibling; e.tag !== 5 && e.tag !== 6 && e.tag !== 18;) {
				if (e.tag === 27 && Sp(e.type) || e.flags & 2 || e.child === null || e.tag === 4) continue a;
				e.child.return = e, e = e.child;
			}
			if (!(e.flags & 2)) return e.stateNode;
		}
	}
	function Il(e, t, n, r) {
		var i = e.tag;
		if (i === 5 || i === 6) i = e.stateNode, t ? (n.nodeType === 9 ? n.body : n.nodeName === "HTML" ? n.ownerDocument.body : n).insertBefore(i, t) : (t = n.nodeType === 9 ? n.body : n.nodeName === "HTML" ? n.ownerDocument.body : n, t.appendChild(i), n = n._reactRootContainer, n != null || t.onclick !== null || (t.onclick = vn)), Dl(e, r), I = !0;
		else if (i !== 4 && (i === 27 && (Dl(e, r), r = null, Sp(e.type) && (n = e.stateNode, t = null)), e = e.child, e !== null)) for (Il(e, t, n, r), e = e.sibling; e !== null;) Il(e, t, n, r), e = e.sibling;
	}
	function Ll(e, t, n, r) {
		var i = e.tag;
		if (i === 5 || i === 6) i = e.stateNode, t ? n.insertBefore(i, t) : n.appendChild(i), Dl(e, r), I = !0;
		else if (i !== 4 && (i === 27 && (Dl(e, r), r = null, Sp(e.type) && (n = e.stateNode)), e = e.child, e !== null)) for (Ll(e, t, n, r), e = e.sibling; e !== null;) Ll(e, t, n, r), e = e.sibling;
	}
	function Rl(e) {
		var t = e.stateNode, n = e.memoizedProps;
		try {
			for (var r = e.type, i = t.attributes; i.length;) t.removeAttributeNode(i[0]);
			np(t, r, n), t[F] = e, t[Et] = n;
		} catch (t) {
			Z(e, e.return, t);
		}
	}
	var zl = !1, Bl = null;
	function Vl(e) {
		(e.tag === 30 || e.subtreeFlags & 33554432) && (zl = !0);
	}
	var Hl = null;
	function Ul() {
		var e = Hl;
		return Hl = null, e;
	}
	var Wl = 0;
	function Gl(e, t, n, r, i) {
		return Wl = 0, Kl(e.child, t, n, r, i);
	}
	function Kl(e, t, n, r, i) {
		for (var a = !1; e !== null;) {
			if (e.tag === 5) {
				var o = e.stateNode;
				if (r !== null) {
					var s = Op(o);
					r.push(s), s.view && (a = !0);
				} else a || Op(o).view && (a = !0);
				zl = !0, Tp(o, Wl === 0 ? t : t + "_" + Wl, n), Wl++;
			} else e.tag === 22 && e.memoizedState !== null || e.tag === 30 && i || Kl(e.child, t, n, r, i) && (a = !0);
			e = e.sibling;
		}
		return a;
	}
	function ql(e, t) {
		for (; e !== null;) e.tag === 5 ? Ep(e.stateNode, e.memoizedProps) : e.tag === 22 && e.memoizedState !== null || e.tag === 30 && t || ql(e.child, t), e = e.sibling;
	}
	function Jl(e) {
		if (e.subtreeFlags & 18874368) for (e = e.child; e !== null;) {
			if ((e.tag !== 22 || e.memoizedState === null) && (Jl(e), e.tag === 30 && e.flags & 18874368 && e.stateNode.paired)) {
				var t = e.memoizedProps;
				if (t.name == null || t.name === "auto") throw Error(s(544));
				var n = t.name;
				t = yi(t.default, t.share), t !== "none" && (Gl(e, n, t, null, !1) || ql(e.child, !1));
			}
			e = e.sibling;
		}
	}
	function Yl(e, t) {
		if (e.tag === 30) {
			var n = e.stateNode, r = e.memoizedProps, i = _i(r, n), a = yi(r.default, n.paired ? r.share : r.enter);
			a === "none" ? Jl(e) : Gl(e, i, a, null, !1) ? (Jl(e), n.paired || t || Nd(e, r.onEnter)) : ql(e.child, !1);
		} else if (e.subtreeFlags & 33554432) for (e = e.child; e !== null;) Yl(e, t), e = e.sibling;
		else Jl(e);
	}
	function Xl(e) {
		if (Bl !== null && Bl.size !== 0) {
			var t = Bl;
			if (e.subtreeFlags & 18874368) for (e = e.child; e !== null;) {
				if (e.tag !== 22 || e.memoizedState === null) {
					if (e.tag === 30 && e.flags & 18874368) {
						var n = e.memoizedProps, r = n.name;
						if (r != null && r !== "auto") {
							var i = t.get(r);
							if (i !== void 0) {
								var a = yi(n.default, n.share);
								if (a !== "none" && (Gl(e, r, a, null, !1) ? (a = e.stateNode, i.paired = a, a.paired = i, Nd(e, n.onShare)) : ql(e.child, !1)), t.delete(r), t.size === 0) break;
							}
						}
					}
					Xl(e);
				}
				e = e.sibling;
			}
		}
	}
	function Zl(e) {
		if (e.tag === 30) {
			var t = e.memoizedProps, n = _i(t, e.stateNode), r = Bl === null ? void 0 : Bl.get(n), i = yi(t.default, r === void 0 ? t.exit : t.share);
			i !== "none" && (Gl(e, n, i, null, !1) ? r === void 0 ? Nd(e, t.onExit) : (i = e.stateNode, r.paired = i, i.paired = r, Bl.delete(n), Nd(e, t.onShare)) : ql(e.child, !1)), Bl !== null && Xl(e);
		} else if (e.subtreeFlags & 33554432) for (e = e.child; e !== null;) Zl(e), e = e.sibling;
		else Bl !== null && Xl(e);
	}
	function Ql(e) {
		for (e = e.child; e !== null;) {
			if (e.tag === 30) {
				var t = e.memoizedProps, n = _i(t, e.stateNode);
				t = yi(t.default, t.update), e.flags &= -5, t !== "none" && Gl(e, n, t, e.memoizedState = [], !1);
			} else e.subtreeFlags & 33554432 && Ql(e);
			e = e.sibling;
		}
	}
	function $l(e) {
		if (e.subtreeFlags & 18874368) for (e = e.child; e !== null;) {
			if (e.tag !== 22 || e.memoizedState === null) {
				if (e.tag === 30 && e.flags & 18874368) {
					var t = e.stateNode;
					t.paired !== null && (t.paired = null, ql(e.child, !1));
				}
				$l(e);
			}
			e = e.sibling;
		}
	}
	function eu(e) {
		if (e.tag === 30) e.stateNode.paired = null, ql(e.child, !1), $l(e);
		else if (e.subtreeFlags & 33554432) for (e = e.child; e !== null;) eu(e), e = e.sibling;
		else $l(e);
	}
	function tu(e) {
		for (e = e.child; e !== null;) e.tag === 30 ? ql(e.child, !1) : e.subtreeFlags & 33554432 && tu(e), e = e.sibling;
	}
	function nu(e, t, n, r, i, a, o) {
		for (var s = !1; t !== null;) {
			if (t.tag === 5) {
				var c = t.stateNode;
				if (a !== null && Wl < a.length) {
					var l = a[Wl], u = Op(c);
					(l.view || u.view) && (s = !0);
					var d;
					if (d = !(e.flags & 4)) {
						if (u.clip) d = !0;
						else {
							d = l.rect;
							var f = u.rect;
							d = d.y !== f.y || d.x !== f.x || d.height !== f.height || d.width !== f.width;
						}
					}
					d && (e.flags |= 4), u.abs ? u = !l.abs : (l = l.rect, u = u.rect, u = l.height !== u.height || l.width !== u.width), u && (e.flags |= 32);
				} else e.flags |= 32;
				e.flags & 4 && Tp(c, Wl === 0 ? n : n + "_" + Wl, i), s && e.flags & 4 || (Hl === null && (Hl = []), Hl.push(c, Wl === 0 ? r : r + "_" + Wl, t.memoizedProps)), Wl++;
			} else (t.tag !== 22 || t.memoizedState === null) && (t.tag === 30 && o ? e.flags |= t.flags & 32 : nu(e, t.child, n, r, i, a, o) && (s = !0));
			t = t.sibling;
		}
		return s;
	}
	function ru(e, t) {
		for (e = e.child; e !== null;) {
			if (e.tag === 30) {
				var n = e.memoizedProps, r = e.stateNode, i = _i(n, r), a = yi(n.default, n.update);
				if (t) {
					r = r.clones;
					var o = r === null ? null : r.map(kp);
				} else o = e.memoizedState, e.memoizedState = null;
				r = e;
				var s = e.child;
				Wl = 0, i = nu(r, s, i, i, a, o, !1), e.flags & 4 && i && (t || Nd(e, n.onUpdate));
			} else e.subtreeFlags & 33554432 && ru(e, t);
			e = e.sibling;
		}
	}
	var iu = !1, G = !1, au = !1, ou = !1, su = typeof WeakSet == "function" ? WeakSet : Set, cu = null, lu = !1, uu = !1, du = !1, fu = !1;
	function pu(e, t, n) {
		if (e = e.containerInfo, sp = gh, e = qr(e), Jr(e)) {
			if ("selectionStart" in e) var r = {
				start: e.selectionStart,
				end: e.selectionEnd
			};
			else a: {
				r = (r = e.ownerDocument) && r.defaultView || window;
				var i = r.getSelection && r.getSelection();
				if (i && i.rangeCount !== 0) {
					r = i.anchorNode;
					var a = i.anchorOffset, o = i.focusNode;
					i = i.focusOffset;
					try {
						r.nodeType, o.nodeType;
					} catch {
						r = null;
						break a;
					}
					var s = 0, c = -1, l = -1, u = 0, d = 0, f = e, p = null;
					b: for (;;) {
						for (var m; f !== r || a !== 0 && f.nodeType !== 3 || (c = s + a), f !== o || i !== 0 && f.nodeType !== 3 || (l = s + i), f.nodeType === 3 && (s += f.nodeValue.length), (m = f.firstChild) !== null;) p = f, f = m;
						for (;;) {
							if (f === e) break b;
							if (p === r && ++u === a && (c = s), p === o && ++d === i && (l = s), (m = f.nextSibling) !== null) break;
							f = p, p = f.parentNode;
						}
						f = m;
					}
					r = c === -1 || l === -1 ? null : {
						start: c,
						end: l
					};
				} else r = null;
			}
			r ||= {
				start: 0,
				end: 0
			};
		} else r = null;
		for (cp = {
			focusedElem: e,
			selectionRange: r
		}, gh = !1, n = (n & 335544064) === n, cu = t, t = n ? 9270 : 1024; cu !== null;) {
			if (e = cu, n && (r = e.deletions, r !== null)) for (a = 0; a < r.length; a++) n && Zl(r[a]);
			if (e.alternate === null && e.flags & 2) n && Vl(e), mu(n);
			else {
				if (e.tag === 22) {
					if (r = e.alternate, e.memoizedState !== null) {
						r !== null && r.memoizedState === null && n && Zl(r), mu(n);
						continue;
					}
					if (r !== null && r.memoizedState !== null) {
						n && Vl(e), mu(n);
						continue;
					}
				}
				r = e.child, (e.subtreeFlags & t) !== 0 && r !== null ? (r.return = e, cu = r) : (n && Ql(e), mu(n));
			}
		}
		Bl = null;
	}
	function mu(e) {
		for (; cu !== null;) {
			var t = cu, n = e, r = t.alternate, i = t.flags;
			switch (t.tag) {
				case 0:
				case 11:
				case 15: break;
				case 1:
					if (i & 1024 && r !== null) {
						n = void 0, i = r.memoizedProps, r = r.memoizedState;
						var a = t.stateNode;
						try {
							var o = Sc(t.type, i);
							n = a.getSnapshotBeforeUpdate(o, r), a.__reactInternalSnapshotBeforeUpdate = n;
						} catch (e) {
							Z(t, t.return, e);
						}
					}
					break;
				case 3:
					if (i & 1024) {
						if (r = t.stateNode.containerInfo, n = r.nodeType, n === 9) nm(r);
						else if (n === 1) switch (r.nodeName) {
							case "HEAD":
							case "HTML":
							case "BODY":
								nm(r);
								break;
							default: r.textContent = "";
						}
					}
					break;
				case 5:
				case 26:
				case 27:
				case 6:
				case 4:
				case 17: break;
				case 30:
					n && r !== null && (n = _i(r.memoizedProps, r.stateNode), i = t.memoizedProps, i = yi(i.default, i.update), i !== "none" && Gl(r, n, i, r.memoizedState = [], !0));
					break;
				default: if (i & 1024) throw Error(s(163));
			}
			if (r = t.sibling, r !== null) {
				r.return = t.return, cu = r;
				break;
			}
			cu = t.return;
		}
	}
	function hu(e, t, n) {
		var r = n.flags;
		switch (n.tag) {
			case 0:
			case 11:
			case 15:
				Fu(e, n), r & 4 && xl(5, n);
				break;
			case 1:
				if (Fu(e, n), r & 4) {
					if (e = n.stateNode, t === null) try {
						e.componentDidMount();
					} catch (e) {
						Z(n, n.return, e);
					}
					else {
						var i = Sc(n.type, t.memoizedProps);
						t = t.memoizedState;
						try {
							e.componentDidUpdate(i, t, e.__reactInternalSnapshotBeforeUpdate);
						} catch (e) {
							Z(n, n.return, e);
						}
					}
				}
				r & 64 && Cl(n), r & 512 && Tl(n, n.return);
				break;
			case 3:
				if (Fu(e, n), r & 64 && (e = n.updateQueue, e !== null)) {
					if (t = null, n.child !== null) switch (n.child.tag) {
						case 27:
						case 5:
							t = n.child.stateNode;
							break;
						case 1: t = n.child.stateNode;
					}
					try {
						wo(e, t);
					} catch (e) {
						Z(n, n.return, e);
					}
				}
				break;
			case 27: t === null && r & 4 && Rl(n);
			case 26:
			case 5:
				Fu(e, n), t === null && r & 4 && Ml(n), r & 512 && Tl(n, n.return);
				break;
			case 12:
				Fu(e, n);
				break;
			case 31:
				Fu(e, n), r & 4 && wu(e, n);
				break;
			case 13:
				Fu(e, n), r & 4 && Tu(e, n), r & 64 && (e = n.memoizedState, e !== null && (e = e.dehydrated, e !== null && (n = _f.bind(null, n), cm(e, n))));
				break;
			case 22:
				if (r = n.memoizedState !== null || iu, !r) {
					var a = t !== null && t.memoizedState !== null || G;
					t = iu, i = G, iu = r, (G = a) && !i ? (r = 2, n.subtreeFlags & 8772 && (r |= 1), Lu(e, n, r)) : Fu(e, n), iu = t, G = i;
				}
				break;
			case 30:
				Fu(e, n), r & 512 && Tl(n, n.return);
				break;
			case 7: r & 512 && Tl(n, n.return);
			default: Fu(e, n);
		}
	}
	function gu(e, t) {
		for (e = e.child; e !== null;) _u(e, t), e = e.sibling;
	}
	function _u(e, t) {
		switch (e.tag) {
			case 5:
			case 26:
				try {
					var n = e.stateNode;
					if (t) {
						var r = n.style;
						typeof r.setProperty == "function" ? r.setProperty("display", "none", "important") : r.display = "none";
					} else {
						var i = e.stateNode, a = e.memoizedProps.style, o = a != null && a.hasOwnProperty("display") ? a.display : null;
						i.style.display = o == null || typeof o == "boolean" ? "" : ("" + o).trim();
					}
				} catch (t) {
					Z(e, e.return, t);
				}
				vu(e, t);
				break;
			case 6:
				try {
					e.stateNode.nodeValue = t ? "" : e.memoizedProps, I = !0;
				} catch (t) {
					Z(e, e.return, t);
				}
				break;
			case 18:
				try {
					var s = e.stateNode;
					t ? wp(s, !0) : wp(e.stateNode, !1);
				} catch (t) {
					Z(e, e.return, t);
				}
				break;
			case 22:
			case 23:
				e.memoizedState === null && gu(e, t);
				break;
			default: gu(e, t);
		}
	}
	function vu(e, t) {
		if (e.subtreeFlags & 67108864) for (e = e.child; e !== null;) {
			a: {
				var n = e, r = t;
				switch (n.tag) {
					case 4:
						_u(n, r);
						break a;
					case 22:
						n.memoizedState === null && vu(n, r);
						break a;
					default: vu(n, r);
				}
			}
			e = e.sibling;
		}
	}
	function yu(e) {
		var t = e.alternate;
		t !== null && (e.alternate = null, yu(t)), e.child = null, e.deletions = null, e.sibling = null, e.tag === 5 && (t = e.stateNode, t !== null && Pt(t)), e.stateNode = null, e.return = null, e.dependencies = null, e.memoizedProps = null, e.memoizedState = null, e.pendingProps = null, e.stateNode = null, e.updateQueue = null;
	}
	var bu = null, xu = !1;
	function Su(e, t, n) {
		for (n = n.child; n !== null;) Cu(e, t, n), n = n.sibling;
	}
	function Cu(e, t, n) {
		if (tt && typeof tt.onCommitFiberUnmount == "function") try {
			tt.onCommitFiberUnmount(et, n);
		} catch {}
		switch (n.tag) {
			case 26:
				G || El(n, t), Su(e, t, n), n.memoizedState ? n.memoizedState.count-- : n.stateNode && !G && (n = n.stateNode, n.parentNode.removeChild(n));
				break;
			case 27:
				G || El(n, t), kl(n);
				var r = bu, i = xu;
				Sp(n.type) && (bu = n.stateNode, xu = !1), Su(e, t, n), gm(n.stateNode, n.type, n.memoizedProps), bu = r, xu = i;
				break;
			case 5: G || El(n, t), kl(n);
			case 6:
				if (n.tag === 6 && kl(n), r = bu, i = xu, bu = null, Su(e, t, n), bu = r, xu = i, bu !== null) {
					if (xu) try {
						(bu.nodeType === 9 ? bu.body : bu.nodeName === "HTML" ? bu.ownerDocument.body : bu).removeChild(n.stateNode), I = !0;
					} catch (e) {
						Z(n, t, e);
					}
					else try {
						bu.removeChild(n.stateNode), I = !0;
					} catch (e) {
						Z(n, t, e);
					}
				}
				break;
			case 18:
				bu !== null && (xu ? (e = bu, Cp(e.nodeType === 9 ? e.body : e.nodeName === "HTML" ? e.ownerDocument.body : e, n.stateNode), Hh(e)) : Cp(bu, n.stateNode));
				break;
			case 4:
				r = bu, i = xu, bu = n.stateNode.containerInfo, xu = !0, Su(e, t, n), bu = r, xu = i;
				break;
			case 0:
			case 11:
			case 14:
			case 15:
				Sl(2, n, t), G || Sl(4, n, t), Su(e, t, n);
				break;
			case 1:
				G || (El(n, t), r = n.stateNode, typeof r.componentWillUnmount == "function" && wl(n, t, r)), Su(e, t, n);
				break;
			case 21:
				Su(e, t, n);
				break;
			case 22:
				G = (r = G) || n.memoizedState !== null, Su(e, t, n), G = r;
				break;
			case 30:
				El(n, t), Su(e, t, n);
				break;
			case 7:
				G || El(n, t), Su(e, t, n);
				break;
			default: Su(e, t, n);
		}
	}
	function wu(e, t) {
		if (t.memoizedState === null && (e = t.alternate, e !== null && (e = e.memoizedState, e !== null))) {
			e = e.dehydrated;
			try {
				Hh(e);
			} catch (e) {
				Z(t, t.return, e);
			}
		}
	}
	function Tu(e, t) {
		if (t.memoizedState === null && (e = t.alternate, e !== null && (e = e.memoizedState, e !== null && (e = e.dehydrated, e !== null)))) try {
			Hh(e);
		} catch (e) {
			Z(t, t.return, e);
		}
	}
	function Eu(e) {
		switch (e.tag) {
			case 31:
			case 13:
			case 19:
				var t = e.stateNode;
				return t === null && (t = e.stateNode = new su()), t;
			case 22: return e = e.stateNode, t = e._retryCache, t === null && (t = e._retryCache = new su()), t;
			default: throw Error(s(435, e.tag));
		}
	}
	function Du(e, t) {
		var n = Eu(e);
		t.forEach(function(t) {
			if (!n.has(t)) {
				n.add(t);
				var r = vf.bind(null, e, t);
				t.then(r, r);
			}
		});
	}
	function Ou(e, t, n) {
		var r = t.deletions;
		if (r !== null) for (var i = 0; i < r.length; i++) {
			var a = r[i], o = e, c = t, l = c;
			a: for (; l !== null;) {
				switch (l.tag) {
					case 27:
						if (Sp(l.type)) {
							bu = l.stateNode, xu = !1;
							break a;
						}
						break;
					case 5:
						bu = l.stateNode, xu = !1;
						break a;
					case 3:
					case 4:
						bu = l.stateNode.containerInfo, xu = !0;
						break a;
				}
				l = l.return;
			}
			if (bu === null) throw Error(s(160));
			Cu(o, c, a), bu = null, xu = !1, o = a.alternate, o !== null && (o.return = null), a.return = null;
		}
		if (t.subtreeFlags & 13886) for (t = t.child; t !== null;) Au(t, e, n), t = t.sibling;
	}
	var ku = null;
	function Au(e, t, n) {
		var r = e.alternate, i = e.flags;
		switch (e.tag) {
			case 0:
			case 11:
			case 14:
			case 15:
				if (i & 4 && (r = e.updateQueue, r = r === null ? null : r.events, r !== null)) for (var a = 0; a < r.length; a++) {
					var o = r[a];
					o.ref.impl = o.nextImpl;
				}
				Ou(t, e, n), ju(e), i & 4 && (Sl(3, e, e.return), xl(3, e), Sl(5, e, e.return));
				break;
			case 1:
				Ou(t, e, n), ju(e), i & 512 && (G || r === null || El(r, r.return)), i & 64 && iu && (e = e.updateQueue, e !== null && (t = e.callbacks, t !== null && (n = e.shared.hiddenCallbacks, e.shared.hiddenCallbacks = n === null ? t : n.concat(t))));
				break;
			case 26:
				if (a = ku, Ou(t, e, n), ju(e), i & 512 && (G || r === null || El(r, r.return)), i & 4) {
					if (i = r === null ? null : r.memoizedState, n = e.memoizedState, r === null) {
						if (n === null) {
							if (e.stateNode === null) {
								if (iu) e.stateNode = fp(e.type, e.memoizedProps, t.containerInfo, e);
								else {
									a: {
										t = e.type, n = e.memoizedProps, i = a.ownerDocument || a;
										b: switch (t) {
											case "title":
												r = i.getElementsByTagName("title")[0], (!r || r[Mt] || r[F] || r.namespaceURI === "http://www.w3.org/2000/svg" || r.hasAttribute("itemprop")) && (r = i.createElement(t), i.head.insertBefore(r, i.querySelector("head > title"))), np(r, t, n), r[F] = e, zt(r), t = r;
												break a;
											case "link":
												if (a = Gm("link", "href", i).get(t + (n.href || ""))) {
													for (o = 0; o < a.length; o++) if (r = a[o], r.getAttribute("href") === (n.href == null || n.href === "" ? null : n.href) && r.getAttribute("rel") === (n.rel == null ? null : n.rel) && r.getAttribute("title") === (n.title == null ? null : n.title) && r.getAttribute("crossorigin") === (n.crossOrigin == null ? null : n.crossOrigin)) {
														a.splice(o, 1);
														break b;
													}
												}
												r = i.createElement(t), np(r, t, n), i.head.appendChild(r);
												break;
											case "meta":
												if (a = Gm("meta", "content", i).get(t + (n.content || ""))) {
													for (o = 0; o < a.length; o++) if (r = a[o], r.getAttribute("content") === (n.content == null ? null : "" + n.content) && r.getAttribute("name") === (n.name == null ? null : n.name) && r.getAttribute("property") === (n.property == null ? null : n.property) && r.getAttribute("http-equiv") === (n.httpEquiv == null ? null : n.httpEquiv) && r.getAttribute("charset") === (n.charSet == null ? null : n.charSet)) {
														a.splice(o, 1);
														break b;
													}
												}
												r = i.createElement(t), np(r, t, n), i.head.appendChild(r);
												break;
											default: throw Error(s(468, t));
										}
										r[F] = e, zt(r), t = r;
									}
									e.stateNode = t;
								}
							} else iu || Km(a, e.type, e.stateNode);
						} else e.stateNode = Bm(a, n, e.memoizedProps);
					} else i === n ? n === null && e.stateNode !== null && Nl(e, e.memoizedProps, r.memoizedProps) : (i === null ? (t = r.stateNode, t === null || G || t.parentNode.removeChild(t)) : i.count--, n === null ? iu || Km(a, e.type, e.stateNode) : Bm(a, n, e.memoizedProps));
				}
				break;
			case 27:
				Ou(t, e, n), ju(e), i & 512 && (G || r === null || El(r, r.return)), r !== null && i & 4 && Nl(e, e.memoizedProps, r.memoizedProps);
				break;
			case 5:
				if (a = au, au = !1, Ou(t, e, n), au = a, ju(e), i & 512 && (G || r === null || El(r, r.return)), e.flags & 32) {
					t = e.stateNode;
					try {
						dn(t, ""), I = !0;
					} catch (t) {
						Z(e, e.return, t);
					}
				}
				i & 4 && e.stateNode != null && (t = e.memoizedProps, Nl(e, t, r === null ? t : r.memoizedProps)), i & 1024 && (ou = !0);
				break;
			case 6:
				if (Ou(t, e, n), ju(e), i & 4) {
					if (e.stateNode === null) throw Error(s(162));
					t = e.memoizedProps, n = e.stateNode;
					try {
						n.nodeValue = t, I = !0;
					} catch (t) {
						Z(e, e.return, t);
					}
				}
				break;
			case 3:
				if (I = !1, Wm = null, a = ku, ku = bm(t.containerInfo), Ou(t, e, n), ku = a, ju(e), i & 4 && r !== null && r.memoizedState.isDehydrated) try {
					Hh(t.containerInfo);
				} catch (t) {
					Z(e, e.return, t);
				}
				ou && (ou = !1, Mu(e)), I = !1;
				break;
			case 4:
				i = au, au = iu, r = Yt(), a = ku, ku = bm(e.stateNode.containerInfo), Ou(t, e, n), ju(e), ku = a, I && uu && (du = !0), I = r, au = i;
				break;
			case 12:
				Ou(t, e, n), ju(e);
				break;
			case 31:
				Ou(t, e, n), ju(e), i & 4 && (t = e.updateQueue, t !== null && (e.updateQueue = null, Du(e, t)));
				break;
			case 13:
				Ou(t, e, n), ju(e), e.child.flags & 8192 && e.memoizedState !== null != (r !== null && r.memoizedState !== null) && (md = Ge()), i & 4 && (t = e.updateQueue, t !== null && (e.updateQueue = null, Du(e, t)));
				break;
			case 22:
				a = e.memoizedState !== null, o = r !== null && r.memoizedState !== null;
				var c = iu, l = G, u = au;
				iu = c || a, au = u || a, G = l || o, Ou(t, e, n), G = l, au = u, iu = c, ju(e), i & 8192 && (t = e.stateNode, t._visibility = a ? t._visibility & -2 : t._visibility | 1, !a || r === null || o || iu || G || (t = o || G, n = iu, r = G, iu = a || iu, G = t, Iu(e, 2), iu = n, G = r), !a && au || gu(e, a)), i & 4 && (t = e.updateQueue, t !== null && (n = t.retryQueue, n !== null && (t.retryQueue = null, Du(e, n))));
				break;
			case 19:
				Ou(t, e, n), ju(e), i & 4 && (t = e.updateQueue, t !== null && (e.updateQueue = null, Du(e, t)));
				break;
			case 30:
				i & 512 && (G || r === null || El(r, r.return)), i = Yt(), a = uu, o = (n & 335544064) === n, c = e.memoizedProps, uu = o && yi(c.default, c.update) !== "none", Ou(t, e, n), ju(e), o && r !== null && I && (e.flags |= 4), uu = a, I = i;
				break;
			case 21: break;
			case 7: i & 512 && (G || r === null || El(r, r.return)), r && r.stateNode !== null && (r.stateNode._fragmentFiber = e);
			default: Ou(t, e, n), ju(e);
		}
	}
	function ju(e) {
		var t = e.flags;
		if (t & 2) {
			try {
				for (var n, r = e.return; r !== null;) {
					if (Pl(r)) {
						n = r;
						break;
					}
					r = r.return;
				}
				r = null;
				for (var i = e.return; i !== null;) {
					if (jl(i)) {
						var a = i.stateNode;
						r === null ? r = [a] : r.push(a);
					}
					if (Al(i)) break;
					i = i.return;
				}
				var o = r;
				if (n == null) throw Error(s(160));
				switch (n.tag) {
					case 27:
						var c = n.stateNode;
						Ll(e, Fl(e), c, o);
						break;
					case 5:
						var l = n.stateNode;
						n.flags & 32 && (dn(l, ""), n.flags &= -33), Ll(e, Fl(e), l, o);
						break;
					case 3:
					case 4:
						var u = n.stateNode.containerInfo;
						Il(e, Fl(e), u, o);
						break;
					default: throw Error(s(161));
				}
			} catch (t) {
				Z(e, e.return, t);
			}
			e.flags &= -3;
		}
		t & 4096 && (e.flags &= -4097);
	}
	function Mu(e) {
		if (e.subtreeFlags & 1024) for (e = e.child; e !== null;) {
			var t = e;
			Mu(t), t.tag === 5 && t.flags & 1024 && (t = t.stateNode, gh = !0, t.reset(), gh = !1), e = e.sibling;
		}
	}
	function Nu(e, t) {
		if (t.subtreeFlags & 9270) for (t = t.child; t !== null;) Pu(t, e), t = t.sibling;
		else ru(t, !1);
	}
	function Pu(e, t) {
		var n = e.alternate;
		if (n === null) Yl(e, !1);
		else switch (e.tag) {
			case 3:
				if (fu = lu = !1, Ul(), Nu(t, e), !lu && !du) {
					if (e = Hl, e !== null) for (var r = 0; r < e.length; r += 3) {
						n = e[r];
						var i = e[r + 1];
						Ep(n, e[r + 2]), n = n.ownerDocument.documentElement, n !== null && n.animate({
							opacity: [0, 0],
							pointerEvents: ["none", "none"]
						}, {
							duration: 0,
							fill: "forwards",
							pseudoElement: "::view-transition-group(" + i + ")"
						});
					}
					e = t.containerInfo, e = e.nodeType === 9 ? e.documentElement : e.ownerDocument.documentElement, e !== null && e.style.viewTransitionName === "" && (e.style.viewTransitionName = "none", e.animate({
						opacity: [0, 0],
						pointerEvents: ["none", "none"]
					}, {
						duration: 0,
						fill: "forwards",
						pseudoElement: "::view-transition-group(root)"
					}), e.animate({
						width: [0, 0],
						height: [0, 0]
					}, {
						duration: 0,
						fill: "forwards",
						pseudoElement: "::view-transition"
					})), fu = !0;
				}
				Hl = null;
				break;
			case 5:
				Nu(t, e);
				break;
			case 4:
				r = lu, lu = !1, Nu(t, e), lu && (du = !0), lu = r;
				break;
			case 22:
				e.memoizedState === null && (n.memoizedState === null ? Nu(t, e) : Yl(e, !1));
				break;
			case 30:
				r = lu, i = Ul(), lu = !1, Nu(t, e), lu && (e.flags |= 4);
				var a = e.memoizedProps, o = e.stateNode;
				t = _i(a, o), o = _i(n.memoizedProps, o);
				var s = yi(a.default, a.update);
				s === "none" ? t = !1 : (a = n.memoizedState, n.memoizedState = null, n = e.child, Wl = 0, t = nu(e, n, t, o, s, a, !0), Wl !== (a === null ? 0 : a.length) && (e.flags |= 32)), e.flags & 4 && t ? (Nd(e, e.memoizedProps.onUpdate), Hl = i) : i !== null && (i.push.apply(i, Hl), Hl = i), lu = e.flags & 32 ? !0 : r;
				break;
			default: Nu(t, e);
		}
	}
	function Fu(e, t) {
		if (t.subtreeFlags & 8772) for (t = t.child; t !== null;) hu(e, t.alternate, t), t = t.sibling;
	}
	function Iu(e, t) {
		for (e = e.child; e !== null;) {
			var n = e, r = t;
			switch (n.tag) {
				case 0:
				case 11:
				case 14:
				case 15:
					Sl(4, n, n.return), Iu(n, r);
					break;
				case 1:
					El(n, n.return);
					var i = n.stateNode;
					typeof i.componentWillUnmount == "function" && wl(n, n.return, i), Iu(n, r);
					break;
				case 27: r & 2 && gm(n.stateNode, n.type, n.memoizedProps);
				case 5:
					El(n, n.return), n.tag !== 5 && n.tag !== 27 || kl(n), Iu(n, r);
					break;
				case 6:
					kl(n);
					break;
				case 26:
					El(n, n.return), i = n.stateNode, n.memoizedState !== null || i === null || G || i.parentNode.removeChild(i), Iu(n, r);
					break;
				case 22:
					n.memoizedState === null && Iu(n, r);
					break;
				case 30:
					El(n, n.return), Iu(n, r);
					break;
				case 7: El(n, n.return);
				default: Iu(n, r);
			}
			e = e.sibling;
		}
	}
	function Lu(e, t, n) {
		for (n = t.subtreeFlags & 8772 ? n : n & -2, t = t.child; t !== null;) {
			var r = t.alternate, i = e, a = t, o = a.flags, s = !!(n & 1);
			switch (a.tag) {
				case 0:
				case 11:
				case 15:
					Lu(i, a, n), xl(4, a);
					break;
				case 1:
					if (Lu(i, a, n), r = a, i = r.stateNode, typeof i.componentDidMount == "function") try {
						i.componentDidMount();
					} catch (e) {
						Z(r, r.return, e);
					}
					if (r = a, i = r.updateQueue, i !== null) {
						var c = r.stateNode;
						try {
							var l = i.shared.hiddenCallbacks;
							if (l !== null) for (i.shared.hiddenCallbacks = null, i = 0; i < l.length; i++) Co(l[i], c);
						} catch (e) {
							Z(r, r.return, e);
						}
					}
					s && o & 64 && Cl(a), Tl(a, a.return);
					break;
				case 27: n & 2 && Rl(a);
				case 5:
					a.tag !== 5 && a.tag !== 27 || Ol(a), Lu(i, a, n), s && r === null && o & 4 && Ml(a), Tl(a, a.return);
					break;
				case 6:
					Ol(a);
					break;
				case 26:
					c = a.stateNode, a.memoizedState !== null || c === null || iu || Km(bm(c.ownerDocument), a.type, c), Lu(i, a, n), s && r === null && o & 4 && Ml(a), Tl(a, a.return);
					break;
				case 12:
					Lu(i, a, n);
					break;
				case 31:
					Lu(i, a, n), s && o & 4 && wu(i, a);
					break;
				case 13:
					Lu(i, a, n), s && o & 4 && Tu(i, a);
					break;
				case 22:
					a.memoizedState === null && Lu(i, a, n), Tl(a, a.return);
					break;
				case 30:
					Lu(i, a, n), Tl(a, a.return);
					break;
				case 7: Tl(a, a.return);
				default: Lu(i, a, n);
			}
			t = t.sibling;
		}
	}
	function Ru(e, t) {
		var n = null;
		e !== null && e.memoizedState !== null && e.memoizedState.cachePool !== null && (n = e.memoizedState.cachePool.pool), e = null, t.memoizedState !== null && t.memoizedState.cachePool !== null && (e = t.memoizedState.cachePool.pool), e !== n && (e != null && e.refCount++, n != null && Ma(n));
	}
	function zu(e, t) {
		e = null, t.alternate !== null && (e = t.alternate.memoizedState.cache), t = t.memoizedState.cache, t !== e && (t.refCount++, e != null && Ma(e));
	}
	function Bu(e, t, n, r) {
		var i = (n & 335544064) === n;
		if (t.subtreeFlags & (i ? 10262 : 10256)) for (t = t.child; t !== null;) Vu(e, t, n, r), t = t.sibling;
		else i && tu(t);
	}
	function Vu(e, t, n, r) {
		var i = (n & 335544064) === n;
		i && t.alternate === null && t.return !== null && t.return.alternate !== null && eu(t);
		var a = t.flags;
		switch (t.tag) {
			case 0:
			case 11:
			case 15:
				Bu(e, t, n, r), a & 2048 && xl(9, t);
				break;
			case 1:
				Bu(e, t, n, r);
				break;
			case 3:
				Bu(e, t, n, r), i && fu && (e = e.containerInfo, e = e.nodeType === 9 ? e.body : e.nodeName === "HTML" ? e.ownerDocument.body : e, e.style.viewTransitionName === "root" && (e.style.viewTransitionName = ""), e = e.ownerDocument.documentElement, e !== null && e.style.viewTransitionName === "none" && (e.style.viewTransitionName = "")), a & 2048 && (a = null, t.alternate !== null && (a = t.alternate.memoizedState.cache), t = t.memoizedState.cache, t !== a && (t.refCount++, a != null && Ma(a)));
				break;
			case 12:
				if (a & 2048) {
					Bu(e, t, n, r), a = t.stateNode;
					try {
						var o = t.memoizedProps, s = o.id, c = o.onPostCommit;
						typeof c == "function" && c(s, t.alternate === null ? "mount" : "update", a.passiveEffectDuration, -0);
					} catch (e) {
						Z(t, t.return, e);
					}
				} else Bu(e, t, n, r);
				break;
			case 31:
				Bu(e, t, n, r);
				break;
			case 13:
				Bu(e, t, n, r);
				break;
			case 23: break;
			case 22:
				o = t.stateNode, s = t.alternate, t.memoizedState === null ? (i && s !== null && s.memoizedState !== null && eu(t), o._visibility & 2 ? Bu(e, t, n, r) : (o._visibility |= 2, Hu(e, t, n, r, !!(t.subtreeFlags & 10256) || !1))) : (i && s !== null && s.memoizedState === null && eu(s), o._visibility & 2 ? Bu(e, t, n, r) : Uu(e, t)), a & 2048 && Ru(s, t);
				break;
			case 24:
				Bu(e, t, n, r), a & 2048 && zu(t.alternate, t);
				break;
			case 30:
				i && (a = t.alternate, a !== null && (ql(a.child, !0), ql(t.child, !0))), Bu(e, t, n, r);
				break;
			default: Bu(e, t, n, r);
		}
	}
	function Hu(e, t, n, r, i) {
		for (i &&= !!(t.subtreeFlags & 10256) || !1, t = t.child; t !== null;) {
			var a = e, o = t, s = n, c = r, l = o.flags;
			switch (o.tag) {
				case 0:
				case 11:
				case 15:
					Hu(a, o, s, c, i), xl(8, o);
					break;
				case 23: break;
				case 22:
					var u = o.stateNode;
					o.memoizedState === null ? (u._visibility |= 2, Hu(a, o, s, c, i)) : u._visibility & 2 ? Hu(a, o, s, c, i) : Uu(a, o), i && l & 2048 && Ru(o.alternate, o);
					break;
				case 24:
					Hu(a, o, s, c, i), i && l & 2048 && zu(o.alternate, o);
					break;
				default: Hu(a, o, s, c, i);
			}
			t = t.sibling;
		}
	}
	function Uu(e, t) {
		if (t.subtreeFlags & 10256) for (t = t.child; t !== null;) {
			var n = e, r = t, i = r.flags;
			switch (r.tag) {
				case 22:
					Uu(n, r), i & 2048 && Ru(r.alternate, r);
					break;
				case 24:
					Uu(n, r), i & 2048 && zu(r.alternate, r);
					break;
				default: Uu(n, r);
			}
			t = t.sibling;
		}
	}
	var Wu = 8192;
	function Gu(e, t, n) {
		if (e.subtreeFlags & Wu) for (e = e.child; e !== null;) Ku(e, t, n), e = e.sibling;
	}
	function Ku(e, t, n) {
		switch (e.tag) {
			case 26:
				Gu(e, t, n), e.flags & Wu && (e.memoizedState === null ? (e = e.stateNode, (t & 335544128) === t && Zm(n, e)) : Qm(n, ku, e.memoizedState, e.memoizedProps));
				break;
			case 5:
				Gu(e, t, n), e.flags & Wu && (e = e.stateNode, (t & 335544128) === t && Zm(n, e));
				break;
			case 3:
			case 4:
				var r = ku;
				ku = bm(e.stateNode.containerInfo), Gu(e, t, n), ku = r;
				break;
			case 22:
				e.memoizedState === null && (r = e.alternate, r !== null && r.memoizedState !== null ? (r = Wu, Wu = 16777216, Gu(e, t, n), Wu = r) : Gu(e, t, n));
				break;
			case 30:
				if ((e.flags & Wu) !== 0 && (r = e.memoizedProps.name, r != null && r !== "auto")) {
					var i = e.stateNode;
					i.paired = null, Bl === null && (Bl = /* @__PURE__ */ new Map()), Bl.set(r, i);
				}
				Gu(e, t, n);
				break;
			default: Gu(e, t, n);
		}
	}
	function qu(e) {
		var t = e.alternate;
		if (t !== null && (e = t.child, e !== null)) {
			t.child = null;
			do
				t = e.sibling, e.sibling = null, e = t;
			while (e !== null);
		}
	}
	function Ju(e) {
		var t = e.deletions;
		if (e.flags & 16) {
			if (t !== null) for (var n = 0; n < t.length; n++) {
				var r = t[n];
				cu = r, Zu(r, e);
			}
			qu(e);
		}
		if (e.subtreeFlags & 10256) for (e = e.child; e !== null;) Yu(e), e = e.sibling;
	}
	function Yu(e) {
		switch (e.tag) {
			case 0:
			case 11:
			case 15:
				Ju(e), e.flags & 2048 && Sl(9, e, e.return);
				break;
			case 3:
				Ju(e);
				break;
			case 12:
				Ju(e);
				break;
			case 22:
				var t = e.stateNode;
				e.memoizedState !== null && t._visibility & 2 && (e.return === null || e.return.tag !== 13) ? (t._visibility &= -3, Xu(e)) : Ju(e);
				break;
			default: Ju(e);
		}
	}
	function Xu(e) {
		var t = e.deletions;
		if (e.flags & 16) {
			if (t !== null) for (var n = 0; n < t.length; n++) {
				var r = t[n];
				cu = r, Zu(r, e);
			}
			qu(e);
		}
		for (e = e.child; e !== null;) {
			switch (t = e, t.tag) {
				case 0:
				case 11:
				case 15:
					Sl(8, t, t.return), Xu(t);
					break;
				case 22:
					n = t.stateNode, n._visibility & 2 && (n._visibility &= -3, Xu(t));
					break;
				default: Xu(t);
			}
			e = e.sibling;
		}
	}
	function Zu(e, t) {
		for (; cu !== null;) {
			var n = cu;
			switch (n.tag) {
				case 0:
				case 11:
				case 15:
					Sl(8, n, t);
					break;
				case 23:
				case 22:
					if (n.memoizedState !== null && n.memoizedState.cachePool !== null) {
						var r = n.memoizedState.cachePool.pool;
						r != null && r.refCount++;
					}
					break;
				case 24: Ma(n.memoizedState.cache);
			}
			if (r = n.child, r !== null) r.return = n, cu = r;
			else a: for (n = e; cu !== null;) {
				r = cu;
				var i = r.sibling, a = r.return;
				if (yu(r), r === n) {
					cu = null;
					break a;
				}
				if (i !== null) {
					i.return = a, cu = i;
					break a;
				}
				cu = a;
			}
		}
	}
	var Qu = {
		getCacheForType: function(e) {
			var t = wa(Aa), n = t.data.get(e);
			return n === void 0 && (n = e(), t.data.set(e, n)), n;
		},
		cacheSignal: function() {
			return wa(Aa).controller.signal;
		}
	}, $u = typeof WeakMap == "function" ? WeakMap : Map, K = 0, q = null, J = null, Y = 0, X = 0, ed = null, td = !1, nd = !1, rd = !1, id = 0, ad = 0, od = 0, sd = 0, cd = 0, ld = 0, ud = 0, dd = null, fd = null, pd = !1, md = 0, hd = 0, gd = Infinity, _d = null, vd = null, yd = 0, bd = null, xd = null, Sd = 0, Cd = 0, wd = null, Td = null, Ed = null, Dd = null, Od = null, kd = 0, Ad = null;
	function jd() {
		return K & 2 && Y !== 0 ? Y & -Y : k.T === null ? Ct() : Pf();
	}
	function Md() {
		if (ld === 0) {
			if (!(Y & 536870912) || V) {
				var e = P;
				P <<= 1, !(P & 3932160) && (P = 262144), ld = e;
			} else ld = 536870912;
		}
		return e = Ao.current, e !== null && (e.flags |= 32), ld;
	}
	function Nd(e, t) {
		if (t != null) {
			var n = e.stateNode, r = n.ref;
			r === null && (r = n.ref = Pp(_i(e.memoizedProps, n))), Dd === null && (Dd = []), Dd.push(t.bind(null, r));
		}
	}
	function Pd(e, t, n) {
		(e === q && (X === 2 || X === 9) || e.cancelPendingCommit !== null) && (Vd(e, 0), Rd(e, Y, ld, !1)), gt(e, n), K & 2 && e === q || (e === q && (!(K & 2) && (sd |= n), ad === 4 && Rd(e, Y, ld, !1)), Ef(e));
	}
	function Fd(e, t, n) {
		if (K & 6) throw Error(s(327));
		var r = !n && !(t & 127) && (t & e.expiredLanes) === 0 || dt(e, t), i = r ? Yd(e, t) : qd(e, t, !0), a = r;
		do {
			if (i === 0) {
				nd && !r && Rd(e, t, 0, !1);
				break;
			}
			if (n = e.current.alternate, a && !Ld(n)) i = qd(e, t, !1), a = !1;
			else {
				if (i === 2) {
					if (a = t, e.errorRecoveryDisabledLanes & a) var o = 0;
					else o = e.pendingLanes & -536870913, o = o === 0 ? o & 536870912 ? 536870912 : 0 : o;
					if (o !== 0) {
						t = o;
						a: {
							var c = e;
							i = dd;
							var l = c.current.memoizedState.isDehydrated;
							if (l && (Vd(c, o).flags |= 256), o = qd(c, o, !1), o !== 2 && o !== 6) {
								if (rd && !l) {
									c.errorRecoveryDisabledLanes |= a, sd |= a, i = 4;
									break a;
								}
								a = fd, fd = i, a !== null && (fd === null ? fd = a : fd.push.apply(fd, a));
							}
							i = o;
						}
						if (a = !1, i !== 2) continue;
					}
				}
				if (i === 1) {
					Vd(e, 0), Rd(e, t, 0, !0);
					break;
				}
				a: {
					switch (r = e, a = i, a) {
						case 0:
						case 1: throw Error(s(345));
						case 4: if ((t & 4194048) !== t && (t & 62914560) !== t) break;
						case 6:
							Rd(r, t, ld, !td);
							break a;
						case 2:
							fd = null;
							break;
						case 3:
						case 5: break;
						default: throw Error(s(329));
					}
					if ((t & 62914560) === t && (i = md + 300 - Ge(), 10 < i)) {
						if (Rd(r, t, ld, !td), ut(r, 0, !0) !== 0) break a;
						Sd = t, r.timeoutHandle = gp(Id.bind(null, r, n, fd, _d, pd, t, ld, sd, ud, td, a, "Throttled", -0, 0), i);
						break a;
					}
					Id(r, n, fd, _d, pd, t, ld, sd, ud, td, a, null, -0, 0);
				}
				break;
			}
		} while (1);
		Ef(e);
	}
	function Id(e, t, n, r, i, a, o, s, c, l, u, d, f, p) {
		e.timeoutHandle = -1;
		var m = t.subtreeFlags, h = (a & 335544064) === a;
		d = null, (h || m & 8192 || (m & 16785408) == 16785408) && (d = {
			stylesheets: null,
			count: 0,
			imgCount: 0,
			imgBytes: 0,
			suspenseyImages: [],
			waitingForImages: !0,
			waitingForViewTransition: !1,
			unsuspend: vn
		}, Bl = null, Ku(t, a, d), h && (m = d, h = e.containerInfo, h = (h.nodeType === 9 ? h : h.ownerDocument).__reactViewTransition, h != null && (m.count++, m.waitingForViewTransition = !0, m = nh.bind(m), h.finished.then(m, m))), m = (a & 62914560) === a ? md - Ge() : (a & 4194048) === a ? hd - Ge() : 0, m = eh(d, m), m !== null) ? (Sd = a, e.cancelPendingCommit = m(nf.bind(null, e, t, a, n, r, i, o, s, c, l, u, d, null, f, p)), Rd(e, a, o, !l)) : nf(e, t, a, n, r, i, o, s, c, l, u, d);
	}
	function Ld(e) {
		for (var t = e;;) {
			var n = t.tag;
			if ((n === 0 || n === 11 || n === 15) && t.flags & 16384 && (n = t.updateQueue, n !== null && (n = n.stores, n !== null))) for (var r = 0; r < n.length; r++) {
				var i = n[r], a = i.getSnapshot;
				i = i.value;
				try {
					if (!Vr(a(), i)) return !1;
				} catch {
					return !1;
				}
			}
			if (n = t.child, t.subtreeFlags & 16384 && n !== null) n.return = t, t = n;
			else {
				if (t === e) break;
				for (; t.sibling === null;) {
					if (t.return === null || t.return === e) return !0;
					t = t.return;
				}
				t.sibling.return = t.return, t = t.sibling;
			}
		}
		return !0;
	}
	function Rd(e, t, n, r) {
		t = ft(e, t), t &= ~cd, t &= ~sd, e.suspendedLanes |= t, e.pingedLanes &= ~t, r && (e.warmLanes |= t), r = e.expirationTimes;
		for (var i = t; 0 < i;) {
			var a = 31 - rt(i), o = 1 << a;
			r[a] = -1, i &= ~o;
		}
		n !== 0 && vt(e, n, t);
	}
	function zd() {
		return K & 6 ? !0 : (Df(0, !1), !1);
	}
	function Bd() {
		if (J !== null) {
			if (X === 0) var e = J.return;
			else e = J, ga = ha = null, is(e), io = null, ao = 0, e = J;
			for (; e !== null;) bl(e.alternate, e), e = e.return;
			J = null;
		}
	}
	function Vd(e, t) {
		var n = e.timeoutHandle;
		return n !== -1 && (e.timeoutHandle = -1, _p(n)), n = e.cancelPendingCommit, n !== null && (e.cancelPendingCommit = null, n()), Sd = 0, Bd(), q = e, J = n = Pi(e.current, null), Y = t, X = 0, ed = null, td = !1, nd = dt(e, t), rd = !1, ud = ld = cd = sd = od = ad = 0, fd = dd = null, pd = !1, id = ft(e, t), wi(), n;
	}
	function Hd(e, t) {
		H = null, k.H = mc, t === Ja || t === Xa ? (t = no(), X = 3) : t === Ya ? (t = no(), X = 4) : X = t === Mc ? 8 : typeof t == "object" && t && typeof t.then == "function" ? 6 : 1, ed = t, J === null && (ad = 1, Ec(e, Hi(t, e.current)));
	}
	function Ud() {
		var e = Ao.current;
		return e === null ? !0 : (Y & 4194048) === Y ? jo === null : (Y & 62914560) === Y || Y & 536870912 ? e === jo : !1;
	}
	function Wd() {
		var e = k.H;
		return k.H = mc, e === null ? mc : e;
	}
	function Gd() {
		var e = k.A;
		return k.A = Qu, e;
	}
	function Kd() {
		ad = 4, td || (Y & 4194048) !== Y && Ao.current !== null || (nd = !0), !(od & 134217727) && !(sd & 134217727) || q === null || Rd(q, Y, ld, !1);
	}
	function qd(e, t, n) {
		var r = K;
		K |= 2;
		var i = Wd(), a = Gd();
		(q !== e || Y !== t) && (_d = null, Vd(e, t)), t = !1;
		var o = ad;
		a: do
			try {
				if (X !== 0 && J !== null) {
					var s = J, c = ed;
					switch (X) {
						case 8:
							Bd(), o = 6;
							break a;
						case 3:
						case 2:
						case 9:
						case 6:
							Ao.current === null && (t = !0);
							var l = X;
							if (X = 0, ed = null, $d(e, s, c, l), n && nd) {
								o = 0;
								break a;
							}
							break;
						default: l = X, X = 0, ed = null, $d(e, s, c, l);
					}
				}
				Jd(), o = ad;
				break;
			} catch (t) {
				Hd(e, t);
			}
		while (1);
		return t && e.shellSuspendCounter++, ga = ha = null, K = r, k.H = i, k.A = a, J === null && (q = null, Y = 0, wi()), o;
	}
	function Jd() {
		for (; J !== null;) Zd(J);
	}
	function Yd(e, t) {
		var n = K;
		K |= 2;
		var r = Wd(), i = Gd();
		q !== e || Y !== t ? (_d = null, gd = Ge() + 500, Vd(e, t)) : nd = dt(e, t);
		a: do
			try {
				if (X !== 0 && J !== null) {
					t = J;
					var a = ed;
					b: switch (X) {
						case 1:
							X = 0, ed = null, $d(e, t, a, 1);
							break;
						case 2:
						case 9:
							if (Qa(a)) {
								X = 0, ed = null, Qd(t);
								break;
							}
							t = function() {
								X !== 2 && X !== 9 || q !== e || (X = 7), Ef(e);
							}, a.then(t, t);
							break a;
						case 3:
							X = 7;
							break a;
						case 4:
							X = 5;
							break a;
						case 7:
							Qa(a) ? (X = 0, ed = null, Qd(t)) : (X = 0, ed = null, $d(e, t, a, 7));
							break;
						case 5:
							var o = null;
							switch (J.tag) {
								case 26: o = J.memoizedState;
								case 5:
								case 27:
									var c = J;
									if (o ? Ym(o) : c.stateNode.complete) {
										X = 0, ed = null;
										var l = c.sibling;
										if (l !== null) J = l;
										else {
											var u = c.return;
											u === null ? J = null : (J = u, ef(u));
										}
										break b;
									}
							}
							X = 0, ed = null, $d(e, t, a, 5);
							break;
						case 6:
							X = 0, ed = null, $d(e, t, a, 6);
							break;
						case 8:
							Bd(), ad = 6;
							break a;
						default: throw Error(s(462));
					}
				}
				Xd();
				break;
			} catch (t) {
				Hd(e, t);
			}
		while (1);
		return ga = ha = null, k.H = r, k.A = i, K = n, J === null ? (q = null, Y = 0, wi(), ad) : 0;
	}
	function Xd() {
		for (; J !== null && !N();) Zd(J);
	}
	function Zd(e) {
		var t = fl(e.alternate, e, id);
		e.memoizedProps = e.pendingProps, t === null ? ef(e) : J = t;
	}
	function Qd(e) {
		var t = e, n = t.alternate;
		switch (t.tag) {
			case 15:
			case 0:
				t = Kc(n, t, t.pendingProps, t.type, void 0, Y);
				break;
			case 11:
				t = Kc(n, t, t.pendingProps, t.type.render, t.ref, Y);
				break;
			case 5:
				is(t);
				var r = t;
				r === ra && (V ? (la(r), r.tag === 5 && r.stateNode != null && (B = r.stateNode)) : (la(r), V = !0));
			default: bl(n, t), t = J = Fi(t, id), t = fl(n, t, id);
		}
		e.memoizedProps = e.pendingProps, t === null ? ef(e) : J = t;
	}
	function $d(e, t, n, r) {
		ga = ha = null, is(t), io = null, ao = 0;
		var i = t.return;
		try {
			if (jc(e, i, t, n, Y)) {
				ad = 1, Ec(e, Hi(n, e.current)), J = null;
				return;
			}
		} catch (t) {
			if (i !== null) throw J = i, t;
			ad = 1, Ec(e, Hi(n, e.current)), J = null;
			return;
		}
		t.flags & 32768 ? (V || r === 1 ? e = !0 : nd || Y & 536870912 ? e = !1 : (td = e = !0, (r === 2 || r === 9 || r === 3 || r === 6) && (r = Ao.current, r !== null && r.tag === 13 && (r.flags |= 16384))), tf(t, e)) : ef(t);
	}
	function ef(e) {
		var t = e;
		do {
			if (t.flags & 32768) {
				tf(t, td);
				return;
			}
			e = t.return;
			var n = vl(t.alternate, t, id);
			if (n !== null) {
				J = n;
				return;
			}
			if (t = t.sibling, t !== null) {
				J = t;
				return;
			}
			J = t = e;
		} while (t !== null);
		ad === 0 && (ad = 5);
	}
	function tf(e, t) {
		do {
			var n = yl(e.alternate, e);
			if (n !== null) {
				n.flags &= 32767, J = n;
				return;
			}
			if (n = e.return, n !== null && (n.flags |= 32768, n.subtreeFlags = 0, n.deletions = null), !t && (e = e.sibling, e !== null)) {
				J = e;
				return;
			}
			J = e = n;
		} while (e !== null);
		ad = 6, J = null;
	}
	function nf(e, t, n, r, i, a, o, c, l, u, d, f) {
		e.cancelPendingCommit = null;
		do
			df();
		while (yd !== 0);
		if (K & 6) throw Error(s(327));
		if (t !== null) {
			if (t === e.current) throw Error(s(177));
			e === q && (J = q = null, Y = 0), xd = t, bd = e, Sd = n, wd = i, Td = r, rf(e, t, n, o, c, l, f);
		}
	}
	function rf(e, t, n, r, i, a, o) {
		var s = t.lanes | t.childLanes;
		if (Cd = s, s |= Ci, _t(e, n, s, r, i, a), Dd = null, (n & 335544064) === n ? (Od = Fa(e), r = 10262) : (Od = null, r = 10256), (t.subtreeFlags & r) !== 0 || (t.flags & r) !== 0 ? (e.callbackNode = null, e.callbackPriority = 0, yf(Ye, function() {
			return ff(), null;
		})) : (e.callbackNode = null, e.callbackPriority = 0), zl = !1, r = !!(t.flags & 13878), t.subtreeFlags & 13878 || r) {
			r = k.T, k.T = null, i = A.p, A.p = 2, a = K, K |= 4;
			try {
				pu(e, t, n);
			} finally {
				K = a, A.p = i, k.T = r;
			}
		}
		yd = 1, zl ? Ed = Mp(o, e.containerInfo, Od, sf, cf, of, lf, ff, af, null, null) : (sf(), cf(), lf());
	}
	function af(e) {
		if (yd !== 0) {
			var t = bd.onRecoverableError;
			t(e, { componentStack: null });
		}
	}
	function of() {
		yd === 3 && (yd = 0, Pu(xd, bd), yd = 4);
	}
	function sf() {
		if (yd === 1) {
			yd = 0;
			var e = bd, t = xd, n = Sd, r = !!(t.flags & 13878);
			if (t.subtreeFlags & 13878 || r) {
				r = k.T, k.T = null;
				var i = A.p;
				A.p = 2;
				var a = K;
				K |= 4;
				try {
					uu = du = !1, Au(t, e, n), n = cp;
					var o = qr(e.containerInfo), s = n.focusedElem, c = n.selectionRange;
					if (o !== s && s && s.ownerDocument && Kr(s.ownerDocument.documentElement, s)) {
						if (c !== null && Jr(s)) {
							var l = c.start, u = c.end;
							if (u === void 0 && (u = l), "selectionStart" in s) s.selectionStart = l, s.selectionEnd = Math.min(u, s.value.length);
							else {
								var d = s.ownerDocument || document, f = d && d.defaultView || window;
								if (f.getSelection) {
									var p = f.getSelection(), m = s.textContent.length, h = Math.min(c.start, m), g = c.end === void 0 ? h : Math.min(c.end, m);
									!p.extend && h > g && (o = g, g = h, h = o);
									var _ = Gr(s, h), v = Gr(s, g);
									if (_ && v && (p.rangeCount !== 1 || p.anchorNode !== _.node || p.anchorOffset !== _.offset || p.focusNode !== v.node || p.focusOffset !== v.offset)) {
										var y = d.createRange();
										y.setStart(_.node, _.offset), p.removeAllRanges(), h > g ? (p.addRange(y), p.extend(v.node, v.offset)) : (y.setEnd(v.node, v.offset), p.addRange(y));
									}
								}
							}
						}
						for (d = [], p = s; p = p.parentNode;) p.nodeType === 1 && d.push({
							element: p,
							left: p.scrollLeft,
							top: p.scrollTop
						});
						for (typeof s.focus == "function" && s.focus(), s = 0; s < d.length; s++) {
							var b = d[s];
							b.element.scrollLeft = b.left, b.element.scrollTop = b.top;
						}
					}
					gh = !!sp, cp = sp = null;
				} finally {
					K = a, A.p = i, k.T = r;
				}
			}
			e.current = t, yd = 2;
		}
	}
	function cf() {
		if (yd === 2) {
			yd = 0;
			var e = bd, t = xd, n = !!(t.flags & 8772);
			if (t.subtreeFlags & 8772 || n) {
				n = k.T, k.T = null;
				var r = A.p;
				A.p = 2;
				var i = K;
				K |= 4;
				try {
					hu(e, t.alternate, t);
				} finally {
					K = i, A.p = r, k.T = n;
				}
			}
			yd = 3;
		}
	}
	function lf() {
		if (yd === 4 || yd === 3) {
			yd = 0;
			var e = Ed;
			Ed = null, We();
			var t = bd, n = xd, r = Sd, i = Td, a = (r & 335544064) === r ? 10262 : 10256;
			if ((n.subtreeFlags & a) !== 0 || (n.flags & a) !== 0 ? yd = 5 : (yd = 0, xd = bd = null, uf(t, t.pendingLanes)), a = t.pendingLanes, a === 0 && (vd = null), St(r), n = n.stateNode, tt && typeof tt.onCommitFiberRoot == "function") try {
				tt.onCommitFiberRoot(et, n, void 0, (n.current.flags & 128) == 128);
			} catch {}
			if (i !== null) {
				n = k.T, a = A.p, A.p = 2, k.T = null;
				try {
					for (var o = t.onRecoverableError, s = 0; s < i.length; s++) {
						var c = i[s];
						o(c.value, { componentStack: c.stack });
					}
				} finally {
					k.T = n, A.p = a;
				}
			}
			if (i = Dd, o = Od, Od = null, i !== null && (Dd = null, o === null && (o = []), e !== null)) for (c = 0; c < i.length; c++) n = (0, i[c])(o), n !== void 0 && e.finished.finally(n);
			Sd & 3 && df(), Ef(t), a = t.pendingLanes, r & 261930 && a & 42 ? t === Ad ? kd++ : (kd = 0, Ad = t) : (kd = 0, Ad = null), Df(0, !1);
		}
	}
	function uf(e, t) {
		(e.pooledCacheLanes &= t) === 0 && (t = e.pooledCache, t != null && (e.pooledCache = null, Ma(t)));
	}
	function df() {
		return Ed !== null && (Ed.skipTransition(), Ed = null), sf(), cf(), lf(), ff();
	}
	function ff() {
		if (yd !== 5) return !1;
		var e = bd, t = Cd;
		Cd = 0;
		var n = St(Sd), r = k.T, i = A.p;
		try {
			A.p = 32 > n ? 32 : n, k.T = null, n = wd, wd = null;
			var a = bd, o = Sd;
			if (yd = 0, xd = bd = null, Sd = 0, K & 6) throw Error(s(331));
			var c = K;
			if (K |= 4, Yu(a.current), Vu(a, a.current, o, n), K = c, Df(0, !1), tt && typeof tt.onPostCommitFiberRoot == "function") try {
				tt.onPostCommitFiberRoot(et, a);
			} catch {}
			return !0;
		} finally {
			A.p = i, k.T = r, uf(e, t);
		}
	}
	function pf(e, t, n) {
		t = Hi(n, t), t = Oc(e.stateNode, t, 2), e = _o(e, t, 2), e !== null && (gt(e, 2), Ef(e));
	}
	function Z(e, t, n) {
		if (e.tag === 3) pf(e, e, n);
		else for (; t !== null;) {
			if (t.tag === 3) {
				pf(t, e, n);
				break;
			}
			if (t.tag === 1) {
				var r = t.stateNode;
				if (typeof t.type.getDerivedStateFromError == "function" || typeof r.componentDidCatch == "function" && (vd === null || !vd.has(r))) {
					e = Hi(n, e), n = kc(2), r = _o(t, n, 2), r !== null && (Ac(n, r, t, e), gt(r, 2), Ef(r));
					break;
				}
			}
			t = t.return;
		}
	}
	function mf(e, t, n) {
		var r = e.pingCache;
		if (r === null) {
			r = e.pingCache = new $u();
			var i = /* @__PURE__ */ new Set();
			r.set(t, i);
		} else i = r.get(t), i === void 0 && (i = /* @__PURE__ */ new Set(), r.set(t, i));
		i.has(n) || (rd = !0, i.add(n), e = hf.bind(null, e, t, n), t.then(e, e));
	}
	function hf(e, t, n) {
		var r = e.pingCache;
		r !== null && r.delete(t), e.pingedLanes |= e.suspendedLanes & n, e.warmLanes &= ~n, q === e && (Y & n) === n && (ad === 4 || ad === 3 && (Y & 62914560) === Y && 300 > Ge() - md ? K & 2 ? cd |= n : Vd(e, 0) : cd |= n, ud === Y && (ud = 0)), Ef(e);
	}
	function gf(e, t) {
		t === 0 && (t = mt()), e = Di(e, t), e !== null && (gt(e, t), Ef(e));
	}
	function _f(e) {
		var t = e.memoizedState, n = 0;
		t !== null && (n = t.retryLane), gf(e, n);
	}
	function vf(e, t) {
		var n = 0;
		switch (e.tag) {
			case 31:
			case 13:
				var r = e.stateNode, i = e.memoizedState;
				i !== null && (n = i.retryLane);
				break;
			case 19:
				r = e.stateNode;
				break;
			case 22:
				r = e.stateNode._retryCache;
				break;
			default: throw Error(s(314));
		}
		r !== null && r.delete(t), gf(e, n);
	}
	function yf(e, t) {
		return M(e, t);
	}
	var bf = null, xf = null, Sf = !1, Cf = !1, wf = !1, Tf = 0;
	function Ef(e) {
		e !== xf && e.next === null && (xf === null ? bf = xf = e : xf = xf.next = e), Cf = !0, Sf || (Sf = !0, Nf());
	}
	function Df(e, t) {
		if (!wf && Cf) {
			wf = !0;
			do
				for (var n = !1, r = bf; r !== null;) {
					if (!t) {
						if (e !== 0) {
							var i = r.pendingLanes;
							if (i === 0) var a = 0;
							else {
								var o = r.suspendedLanes, s = r.pingedLanes;
								a = (1 << 31 - rt(42 | e) + 1) - 1, a &= i & ~(o & ~s), a = a & 201326741 ? a & 201326741 | 1 : a ? a | 2 : 0;
							}
							a !== 0 && (n = !0, Mf(r, a));
						} else a = Y, a = ut(r, r === q ? a : 0, r.cancelPendingCommit !== null || r.timeoutHandle !== -1), !(a & 3) || dt(r, a) || (n = !0, Mf(r, a));
					}
					r = r.next;
				}
			while (n);
			wf = !1;
		}
	}
	function Of() {
		kf();
	}
	function kf() {
		Cf = Sf = !1;
		var e = 0;
		Tf !== 0 && hp() && (e = Tf);
		for (var t = Ge(), n = null, r = bf; r !== null;) {
			var i = r.next, a = Af(r, t);
			a === 0 ? (r.next = null, n === null ? bf = i : n.next = i, i === null && (xf = n)) : (n = r, (e !== 0 || a & 3) && (Cf = !0)), r = i;
		}
		yd !== 0 && yd !== 5 || Df(e, !1), Tf !== 0 && (Tf = 0);
	}
	function Af(e, t) {
		for (var n = e.suspendedLanes, r = e.pingedLanes, i = e.expirationTimes, a = e.pendingLanes & -62914561; 0 < a;) {
			var o = 31 - rt(a), s = 1 << o, c = i[o];
			c === -1 ? ((s & n) === 0 || (s & r) !== 0) && (i[o] = pt(s, t)) : c <= t && (e.expiredLanes |= s), a &= ~s;
		}
		if (t = q, n = Y, n = ut(e, e === t ? n : 0, e.cancelPendingCommit !== null || e.timeoutHandle !== -1), r = e.callbackNode, n === 0 || e === t && (X === 2 || X === 9) || e.cancelPendingCommit !== null) return r !== null && r !== null && Ue(r), e.callbackNode = null, e.callbackPriority = 0;
		if (!(n & 3) || dt(e, n)) {
			if (t = n & -n, t === e.callbackPriority) return t;
			switch (r !== null && Ue(r), St(n)) {
				case 2:
				case 8:
					n = Je;
					break;
				case 32:
					n = Ye;
					break;
				case 268435456:
					n = Ze;
					break;
				default: n = Ye;
			}
			return r = jf.bind(null, e), n = M(n, r), e.callbackPriority = t, e.callbackNode = n, t;
		}
		return r !== null && r !== null && Ue(r), e.callbackPriority = 2, e.callbackNode = null, 2;
	}
	function jf(e, t) {
		if (yd !== 0 && yd !== 5) return e.callbackNode = null, e.callbackPriority = 0, null;
		var n = e.callbackNode;
		if (df() && e.callbackNode !== n) return null;
		var r = Y;
		return r = ut(e, e === q ? r : 0, e.cancelPendingCommit !== null || e.timeoutHandle !== -1), r === 0 ? null : (Fd(e, r, t), Af(e, Ge()), e.callbackNode != null && e.callbackNode === n ? jf.bind(null, e) : null);
	}
	function Mf(e, t) {
		if (df()) return null;
		Fd(e, t, !0);
	}
	function Nf() {
		bp(function() {
			K & 6 ? M(qe, Of) : kf();
		});
	}
	function Pf() {
		if (Tf === 0) {
			var e = Ra;
			e === 0 && (e = st, st <<= 1, !(st & 261888) && (st = 256)), Tf = e;
		}
		return Tf;
	}
	function Ff(e) {
		return e == null || typeof e == "symbol" || typeof e == "boolean" ? null : typeof e == "function" ? e : _n(e);
	}
	function If(e, t, n, r, i) {
		if (t === "submit" && n && n.stateNode === i) {
			var a = Ff((i[Et] || null).action), o = r.submitter;
			o && (t = (t = o[Et] || null) ? Ff(t.formAction) : o.getAttribute("formAction"), t !== null && (a = t, o = null));
			var s = new zn("action", "action", null, r, i);
			e.push({
				event: s,
				listeners: [{
					instance: null,
					listener: function() {
						if (r.defaultPrevented) {
							if (Tf !== 0) {
								var e = new FormData(i, o);
								ec(n, {
									pending: !0,
									data: e,
									method: i.method,
									action: a
								}, null, e);
							}
						} else typeof a == "function" && (s.preventDefault(), e = new FormData(i, o), ec(n, {
							pending: !0,
							data: e,
							method: i.method,
							action: a
						}, a, e));
					},
					currentTarget: i
				}]
			});
		}
	}
	for (var Lf = 0; Lf < mi.length; Lf++) {
		var Rf = mi[Lf];
		hi(Rf.toLowerCase(), "on" + (Rf[0].toUpperCase() + Rf.slice(1)));
	}
	hi(oi, "onAnimationEnd"), hi(si, "onAnimationIteration"), hi(ci, "onAnimationStart"), hi("dblclick", "onDoubleClick"), hi("focusin", "onFocus"), hi("focusout", "onBlur"), hi(li, "onTransitionRun"), hi(ui, "onTransitionStart"), hi(di, "onTransitionCancel"), hi(fi, "onTransitionEnd"), Wt("onMouseEnter", ["mouseout", "mouseover"]), Wt("onMouseLeave", ["mouseout", "mouseover"]), Wt("onPointerEnter", ["pointerout", "pointerover"]), Wt("onPointerLeave", ["pointerout", "pointerover"]), Ut("onChange", "change click focusin focusout input keydown keyup selectionchange".split(" ")), Ut("onSelect", "focusout contextmenu dragend focusin keydown keyup mousedown mouseup selectionchange".split(" ")), Ut("onBeforeInput", [
		"compositionend",
		"keypress",
		"textInput",
		"paste"
	]), Ut("onCompositionEnd", "compositionend focusout keydown keypress keyup mousedown".split(" ")), Ut("onCompositionStart", "compositionstart focusout keydown keypress keyup mousedown".split(" ")), Ut("onCompositionUpdate", "compositionupdate focusout keydown keypress keyup mousedown".split(" "));
	var zf = "abort canplay canplaythrough durationchange emptied encrypted ended error loadeddata loadedmetadata loadstart pause play playing progress ratechange resize seeked seeking stalled suspend timeupdate volumechange waiting".split(" "), Bf = new Set("beforetoggle cancel close invalid load scroll scrollend toggle".split(" ").concat(zf));
	function Vf(e, t) {
		t = !!(t & 4);
		for (var n = 0; n < e.length; n++) {
			var r = e[n], i = r.event;
			r = r.listeners;
			a: {
				var a = void 0;
				if (t) for (var o = r.length - 1; 0 <= o; o--) {
					var s = r[o], c = s.instance, l = s.currentTarget;
					if (s = s.listener, c !== a && i.isPropagationStopped()) break a;
					a = s, i.currentTarget = l;
					try {
						a(i);
					} catch (e) {
						bi(e);
					}
					i.currentTarget = null, a = c;
				}
				else for (o = 0; o < r.length; o++) {
					if (s = r[o], c = s.instance, l = s.currentTarget, s = s.listener, c !== a && i.isPropagationStopped()) break a;
					a = s, i.currentTarget = l;
					try {
						a(i);
					} catch (e) {
						bi(e);
					}
					i.currentTarget = null, a = c;
				}
			}
		}
	}
	function Q(e, t) {
		var n = t[Ot];
		n === void 0 && (n = t[Ot] = /* @__PURE__ */ new Set());
		var r = e + "__bubble";
		n.has(r) || (Gf(t, e, 2, !1), n.add(r));
	}
	function Hf(e, t, n) {
		var r = 0;
		t && (r |= 4), Gf(n, e, r, t);
	}
	var Uf = "_reactListening" + Math.random().toString(36).slice(2);
	function Wf(e) {
		if (!e[Uf]) {
			e[Uf] = !0, Vt.forEach(function(t) {
				t !== "selectionchange" && (Bf.has(t) || Hf(t, !1, e), Hf(t, !0, e));
			});
			var t = e.nodeType === 9 ? e : e.ownerDocument;
			t === null || t[Uf] || (t[Uf] = !0, Hf("selectionchange", !1, t));
		}
	}
	function Gf(e, t, n, r) {
		switch (Ch(t)) {
			case 2:
				var i = _h;
				break;
			case 8:
				i = vh;
				break;
			default: i = yh;
		}
		n = i.bind(null, t, n, e), i = void 0, !On || t !== "touchstart" && t !== "touchmove" && t !== "wheel" || (i = !0), r ? i === void 0 ? e.addEventListener(t, n, !0) : e.addEventListener(t, n, {
			capture: !0,
			passive: i
		}) : i === void 0 ? e.addEventListener(t, n, !1) : e.addEventListener(t, n, { passive: i });
	}
	function Kf(e, t, n, r, i) {
		var a = r;
		if (!(t & 1) && !(t & 2) && r !== null) a: for (;;) {
			if (r === null) return;
			var o = r.tag;
			if (o === 3 || o === 4) {
				var s = r.stateNode.containerInfo;
				if (s === i) break;
				if (o === 4) for (o = r.return; o !== null;) {
					var c = o.tag;
					if ((c === 3 || c === 4) && o.stateNode.containerInfo === i) return;
					o = o.return;
				}
				for (; s !== null;) {
					if (o = Ft(s), o === null) return;
					if (c = o.tag, c === 5 || c === 6 || c === 26 || c === 27) {
						r = a = o;
						continue a;
					}
					s = s.parentNode;
				}
			}
			r = r.return;
		}
		Tn(function() {
			var r = a, i = bn(n), o = [];
			a: {
				var s = pi.get(e);
				if (s !== void 0) {
					var c = zn, u = e;
					switch (e) {
						case "keypress": if (Pn(n) === 0) break a;
						case "keydown":
						case "keyup":
							c = rr;
							break;
						case "focusin":
							u = "focus", c = Jn;
							break;
						case "focusout":
							u = "blur", c = Jn;
							break;
						case "beforeblur":
						case "afterblur":
							c = Jn;
							break;
						case "click": if (n.button === 2) break a;
						case "auxclick":
						case "dblclick":
						case "mousedown":
						case "mousemove":
						case "mouseup":
						case "mouseout":
						case "mouseover":
						case "contextmenu":
							c = Kn;
							break;
						case "drag":
						case "dragend":
						case "dragenter":
						case "dragexit":
						case "dragleave":
						case "dragover":
						case "dragstart":
						case "drop":
							c = qn;
							break;
						case "touchcancel":
						case "touchend":
						case "touchmove":
						case "touchstart":
							c = or;
							break;
						case oi:
						case si:
						case ci:
							c = Yn;
							break;
						case fi:
							c = sr;
							break;
						case "scroll":
						case "scrollend":
							c = Vn;
							break;
						case "wheel":
							c = cr;
							break;
						case "copy":
						case "cut":
						case "paste":
							c = Xn;
							break;
						case "gotpointercapture":
						case "lostpointercapture":
						case "pointercancel":
						case "pointerdown":
						case "pointermove":
						case "pointerout":
						case "pointerover":
						case "pointerup":
							c = ir;
							break;
						case "submit":
							c = ar;
							break;
						case "toggle":
						case "beforetoggle": c = lr;
					}
					var d = !!(t & 4), f = !d && (e === "scroll" || e === "scrollend"), p = d ? s === null ? null : s + "Capture" : s;
					d = [];
					for (var m = r, h; m !== null;) {
						var g = m;
						if (h = g.stateNode, g = g.tag, g !== 5 && g !== 26 && g !== 27 || h === null || p === null || (g = En(m, p), g != null && d.push(qf(m, g, h))), f) break;
						m = m.return;
					}
					0 < d.length && (s = new c(s, u, null, n, i), o.push({
						event: s,
						listeners: d
					}));
				}
			}
			if (!(t & 7)) {
				a: {
					if (c = e === "mouseover" || e === "pointerover", s = e === "mouseout" || e === "pointerout", c && n !== yn && (u = n.relatedTarget || n.fromElement) && (Ft(u) || u[Dt])) break a;
					(s || c) && (u = i.window === i ? i : (c = i.ownerDocument) ? c.defaultView || c.parentWindow : window, s ? (c = n.relatedTarget || n.toElement, s = r, c = c ? Ft(c) : null, c !== null && (f = l(c), d = c.tag, c !== f || d !== 5 && d !== 27 && d !== 6) && (c = null)) : (s = null, c = r), s !== c && (d = Kn, g = "onMouseLeave", p = "onMouseEnter", m = "mouse", (e === "pointerout" || e === "pointerover") && (d = ir, g = "onPointerLeave", p = "onPointerEnter", m = "pointer"), f = s == null ? u : Lt(s), h = c == null ? u : Lt(c), u = new d(g, m + "leave", s, n, i), u.target = f, u.relatedTarget = h, g = null, Ft(i) === r && (d = new d(p, m + "enter", c, n, i), d.target = h, d.relatedTarget = f, g = d), f = g, d = s && c ? w(s, c, Yf) : null, s !== null && Xf(o, u, s, d, !1), c !== null && f !== null && Xf(o, f, c, d, !0)));
				}
				a: {
					if (s = r ? Lt(r) : window, c = s.nodeName && s.nodeName.toLowerCase(), c === "select" || c === "input" && s.type === "file") var _ = kr;
					else if (Cr(s)) {
						if (Ar) _ = zr;
						else {
							_ = Lr;
							var v = Ir;
						}
					} else c = s.nodeName, !c || c.toLowerCase() !== "input" || s.type !== "checkbox" && s.type !== "radio" ? r && mn(r.elementType) && (_ = kr) : _ = Rr;
					if (_ &&= _(e, r)) {
						wr(o, _, n, i);
						break a;
					}
					v && v(e, s, r);
				}
				switch (v = r ? Lt(r) : window, e) {
					case "focusin":
						(Cr(v) || v.contentEditable === "true") && (Xr = v, Zr = r, Qr = null);
						break;
					case "focusout":
						Qr = Zr = Xr = null;
						break;
					case "mousedown":
						$r = !0;
						break;
					case "contextmenu":
					case "mouseup":
					case "dragend":
						$r = !1, ei(o, n, i);
						break;
					case "selectionchange": if (Yr) break;
					case "keydown":
					case "keyup": ei(o, n, i);
				}
				var y;
				if (dr) b: {
					switch (e) {
						case "compositionstart":
							var b = "onCompositionStart";
							break b;
						case "compositionend":
							b = "onCompositionEnd";
							break b;
						case "compositionupdate":
							b = "onCompositionUpdate";
							break b;
					}
					b = void 0;
				}
				else yr ? _r(e, n) && (b = "onCompositionEnd") : e === "keydown" && n.keyCode === 229 && (b = "onCompositionStart");
				b && (mr && n.locale !== "ko" && (yr || b !== "onCompositionStart" ? b === "onCompositionEnd" && yr && (y = Nn()) : (An = i, jn = "value" in An ? An.value : An.textContent, yr = !0)), v = Jf(r, b), 0 < v.length && (b = new Zn(b, e, null, n, i), o.push({
					event: b,
					listeners: v
				}), y ? b.data = y : (y = vr(n), y !== null && (b.data = y)))), (y = pr ? br(e, n) : xr(e, n)) && (b = Jf(r, "onBeforeInput"), 0 < b.length && (v = new Zn("onBeforeInput", "beforeinput", null, n, i), o.push({
					event: v,
					listeners: b
				}), v.data = y)), If(o, e, r, n, i);
			}
			Vf(o, t);
		});
	}
	function qf(e, t, n) {
		return {
			instance: e,
			listener: t,
			currentTarget: n
		};
	}
	function Jf(e, t) {
		for (var n = t + "Capture", r = []; e !== null;) {
			var i = e, a = i.stateNode;
			if (i = i.tag, i !== 5 && i !== 26 && i !== 27 || a === null || (i = En(e, n), i != null && r.unshift(qf(e, i, a)), i = En(e, t), i != null && r.push(qf(e, i, a))), e.tag === 3) return r;
			e = e.return;
		}
		return [];
	}
	function Yf(e) {
		if (e === null) return null;
		do
			e = e.return;
		while (e && e.tag !== 5 && e.tag !== 27);
		return e || null;
	}
	function Xf(e, t, n, r, i) {
		for (var a = t._reactName, o = []; n !== null && n !== r;) {
			var s = n, c = s.alternate, l = s.stateNode;
			if (s = s.tag, c !== null && c === r) break;
			s !== 5 && s !== 26 && s !== 27 || l === null || (c = l, i ? (l = En(n, a), l != null && o.unshift(qf(n, l, c))) : i || (l = En(n, a), l != null && o.push(qf(n, l, c)))), n = n.return;
		}
		o.length !== 0 && e.push({
			event: t,
			listeners: o
		});
	}
	var Zf = /\r\n?/g, Qf = /\u0000|\uFFFD/g;
	function $f(e) {
		return (typeof e == "string" ? e : "" + e).replace(Zf, "\n").replace(Qf, "");
	}
	function ep(e, t) {
		return t = $f(t), $f(e) === t;
	}
	function $(e, t, n, r, i, a) {
		switch (n) {
			case "children":
				if (typeof r == "string") t === "body" || t === "textarea" && r === "" || dn(e, r);
				else if (typeof r == "number" || typeof r == "bigint") t !== "body" && dn(e, "" + r);
				else return;
				break;
			case "className":
				Zt(e, "class", r);
				break;
			case "tabIndex":
				Zt(e, "tabindex", r);
				break;
			case "dir":
			case "role":
			case "viewBox":
			case "width":
			case "height":
				Zt(e, n, r);
				break;
			case "style":
				z(e, r, a);
				return;
			case "data": if (t !== "object") {
				Zt(e, "data", r);
				break;
			}
			case "src":
			case "href":
				if (r === "" && (t !== "a" || n !== "href") || r == null || typeof r == "function" || typeof r == "symbol" || typeof r == "boolean") {
					e.removeAttribute(n);
					break;
				}
				r = _n(r), e.setAttribute(n, r);
				break;
			case "action":
			case "formAction":
				if (typeof r == "function") {
					e.setAttribute(n, "javascript:throw new Error('A React form was unexpectedly submitted. If you called form.submit() manually, consider using form.requestSubmit() instead. If you\\'re trying to use event.stopPropagation() in a submit event handler, consider also calling event.preventDefault().')");
					break;
				}
				if (typeof a == "function" && (n === "formAction" ? (t !== "input" && $(e, t, "name", i.name, i, null), $(e, t, "formEncType", i.formEncType, i, null), $(e, t, "formMethod", i.formMethod, i, null), $(e, t, "formTarget", i.formTarget, i, null)) : ($(e, t, "encType", i.encType, i, null), $(e, t, "method", i.method, i, null), $(e, t, "target", i.target, i, null))), r == null || typeof r == "symbol" || typeof r == "boolean") {
					e.removeAttribute(n);
					break;
				}
				r = _n(r), e.setAttribute(n, r);
				break;
			case "onClick":
				r != null && (e.onclick = vn);
				return;
			case "onScroll":
				r != null && Q("scroll", e);
				return;
			case "onScrollEnd":
				r != null && Q("scrollend", e);
				return;
			case "dangerouslySetInnerHTML":
				if (r != null) {
					if (typeof r != "object" || !("__html" in r)) throw Error(s(61));
					if (n = r.__html, n != null) {
						if (i.children != null) throw Error(s(60));
						a?.__html !== n && (e.innerHTML = n);
					}
				}
				break;
			case "multiple":
				e.multiple = r && typeof r != "function" && typeof r != "symbol";
				break;
			case "muted":
				e.muted = r && typeof r != "function" && typeof r != "symbol";
				break;
			case "suppressContentEditableWarning":
			case "suppressHydrationWarning":
			case "defaultValue":
			case "defaultChecked":
			case "innerHTML":
			case "ref": break;
			case "autoFocus": break;
			case "xlinkHref":
				if (r == null || typeof r == "function" || typeof r == "boolean" || typeof r == "symbol") {
					e.removeAttribute("xlink:href");
					break;
				}
				n = _n(r), e.setAttributeNS("http://www.w3.org/1999/xlink", "xlink:href", n);
				break;
			case "contentEditable":
			case "spellCheck":
			case "draggable":
			case "value":
			case "autoReverse":
			case "externalResourcesRequired":
			case "focusable":
			case "preserveAlpha":
				r != null && typeof r != "function" && typeof r != "symbol" ? e.setAttribute(n, r) : e.removeAttribute(n);
				break;
			case "inert":
			case "allowFullScreen":
			case "async":
			case "autoPlay":
			case "controls":
			case "credentialless":
			case "default":
			case "defer":
			case "disabled":
			case "disablePictureInPicture":
			case "disableRemotePlayback":
			case "formNoValidate":
			case "hidden":
			case "loop":
			case "noModule":
			case "noValidate":
			case "open":
			case "playsInline":
			case "readOnly":
			case "required":
			case "reversed":
			case "scoped":
			case "seamless":
			case "itemScope":
				r && typeof r != "function" && typeof r != "symbol" ? e.setAttribute(n, "") : e.removeAttribute(n);
				break;
			case "capture":
			case "download":
				!0 === r ? e.setAttribute(n, "") : !1 !== r && r != null && typeof r != "function" && typeof r != "symbol" ? e.setAttribute(n, r) : e.removeAttribute(n);
				break;
			case "cols":
			case "rows":
			case "size":
			case "span":
				r != null && typeof r != "function" && typeof r != "symbol" && !isNaN(r) && 1 <= r ? e.setAttribute(n, r) : e.removeAttribute(n);
				break;
			case "rowSpan":
			case "start":
				r == null || typeof r == "function" || typeof r == "symbol" || isNaN(r) ? e.removeAttribute(n) : e.setAttribute(n, r);
				break;
			case "popover":
				Q("beforetoggle", e), Q("toggle", e), Xt(e, "popover", r);
				break;
			case "xlinkActuate":
				Qt(e, "http://www.w3.org/1999/xlink", "xlink:actuate", r);
				break;
			case "xlinkArcrole":
				Qt(e, "http://www.w3.org/1999/xlink", "xlink:arcrole", r);
				break;
			case "xlinkRole":
				Qt(e, "http://www.w3.org/1999/xlink", "xlink:role", r);
				break;
			case "xlinkShow":
				Qt(e, "http://www.w3.org/1999/xlink", "xlink:show", r);
				break;
			case "xlinkTitle":
				Qt(e, "http://www.w3.org/1999/xlink", "xlink:title", r);
				break;
			case "xlinkType":
				Qt(e, "http://www.w3.org/1999/xlink", "xlink:type", r);
				break;
			case "xmlBase":
				Qt(e, "http://www.w3.org/XML/1998/namespace", "xml:base", r);
				break;
			case "xmlLang":
				Qt(e, "http://www.w3.org/XML/1998/namespace", "xml:lang", r);
				break;
			case "xmlSpace":
				Qt(e, "http://www.w3.org/XML/1998/namespace", "xml:space", r);
				break;
			case "is":
				Xt(e, "is", r);
				break;
			case "innerText":
			case "textContent": return;
			default: if (!(2 < n.length) || n[0] !== "o" && n[0] !== "O" || n[1] !== "n" && n[1] !== "N") n = hn.get(n) || n, Xt(e, n, r);
			else return;
		}
		I = !0;
	}
	function tp(e, t, n, r, i, a) {
		switch (n) {
			case "style":
				z(e, r, a);
				return;
			case "dangerouslySetInnerHTML":
				if (r != null) {
					if (typeof r != "object" || !("__html" in r)) throw Error(s(61));
					if (n = r.__html, n != null) {
						if (i.children != null) throw Error(s(60));
						a?.__html !== n && (e.innerHTML = n);
					}
				}
				break;
			case "children":
				if (typeof r == "string") dn(e, r);
				else if (typeof r == "number" || typeof r == "bigint") dn(e, "" + r);
				else return;
				break;
			case "onScroll":
				r != null && Q("scroll", e);
				return;
			case "onScrollEnd":
				r != null && Q("scrollend", e);
				return;
			case "onClick":
				r != null && (e.onclick = vn);
				return;
			case "suppressContentEditableWarning":
			case "suppressHydrationWarning":
			case "innerHTML":
			case "ref": return;
			case "innerText":
			case "textContent": return;
			default:
				if (!Ht.hasOwnProperty(n)) a: {
					if (n[0] === "o" && n[1] === "n" && (i = n.endsWith("Capture"), a = n.slice(2, i ? n.length - 7 : void 0), t = e[Et] || null, t = t == null ? null : t[n], typeof t == "function" && e.removeEventListener(a, t, i), typeof r == "function")) {
						typeof t != "function" && t !== null && (n in e ? e[n] = null : e.hasAttribute(n) && e.removeAttribute(n)), e.addEventListener(a, r, i);
						break a;
					}
					I = !0, n in e ? e[n] = r : !0 === r ? e.setAttribute(n, "") : Xt(e, n, r);
				}
				return;
		}
		I = !0;
	}
	function np(e, t, n) {
		switch (t) {
			case "div":
			case "span":
			case "svg":
			case "path":
			case "a":
			case "g":
			case "p":
			case "li": break;
			case "img":
				Q("error", e), Q("load", e);
				var r = !1, i = !1, a;
				for (a in n) if (n.hasOwnProperty(a)) {
					var o = n[a];
					if (o != null) switch (a) {
						case "src":
							r = !0;
							break;
						case "srcSet":
							i = !0;
							break;
						case "children":
						case "dangerouslySetInnerHTML": throw Error(s(137, t));
						default: $(e, t, a, o, n, null);
					}
				}
				i && $(e, t, "srcSet", n.srcSet, n, null), r && $(e, t, "src", n.src, n, null);
				return;
			case "input":
				Q("invalid", e);
				var c = a = o = i = null, l = null, u = null;
				for (r in n) if (n.hasOwnProperty(r)) {
					var d = n[r];
					if (d != null) switch (r) {
						case "name":
							i = d;
							break;
						case "type":
							o = d;
							break;
						case "checked":
							l = d;
							break;
						case "defaultChecked":
							u = d;
							break;
						case "value":
							a = d;
							break;
						case "defaultValue":
							c = d;
							break;
						case "children":
						case "dangerouslySetInnerHTML":
							if (d != null) throw Error(s(137, t));
							break;
						default: $(e, t, r, d, n, null);
					}
				}
				on(e, a, c, l, u, o, i, !1);
				return;
			case "select":
				for (i in Q("invalid", e), r = o = a = null, n) if (n.hasOwnProperty(i) && (c = n[i], c != null)) switch (i) {
					case "value":
						a = c;
						break;
					case "defaultValue":
						o = c;
						break;
					case "multiple": r = c;
					default: $(e, t, i, c, n, null);
				}
				t = a, n = o, e.multiple = !!r, t == null ? n != null && cn(e, !!r, n, !0) : cn(e, !!r, t, !1);
				return;
			case "textarea":
				for (o in Q("invalid", e), a = i = r = null, n) if (n.hasOwnProperty(o) && (c = n[o], c != null)) switch (o) {
					case "value":
						r = c;
						break;
					case "defaultValue":
						i = c;
						break;
					case "children":
						a = c;
						break;
					case "dangerouslySetInnerHTML":
						if (c != null) throw Error(s(91));
						break;
					default: $(e, t, o, c, n, null);
				}
				un(e, r, i, a);
				return;
			case "option":
				for (l in n) if (n.hasOwnProperty(l) && (r = n[l], r != null)) switch (l) {
					case "selected":
						e.selected = r && typeof r != "function" && typeof r != "symbol";
						break;
					default: $(e, t, l, r, n, null);
				}
				return;
			case "dialog":
				Q("beforetoggle", e), Q("toggle", e), Q("cancel", e), Q("close", e);
				break;
			case "iframe":
			case "object":
				Q("load", e);
				break;
			case "video":
			case "audio":
				for (r = 0; r < zf.length; r++) Q(zf[r], e);
				break;
			case "image":
				Q("error", e), Q("load", e);
				break;
			case "details":
				Q("toggle", e);
				break;
			case "embed":
			case "source":
			case "link": Q("error", e), Q("load", e);
			case "area":
			case "base":
			case "br":
			case "col":
			case "hr":
			case "keygen":
			case "meta":
			case "param":
			case "track":
			case "wbr":
			case "menuitem":
				for (u in n) if (n.hasOwnProperty(u) && (r = n[u], r != null)) switch (u) {
					case "children":
					case "dangerouslySetInnerHTML": throw Error(s(137, t));
					default: $(e, t, u, r, n, null);
				}
				return;
			default: if (mn(t)) {
				for (d in n) n.hasOwnProperty(d) && (r = n[d], r !== void 0 && tp(e, t, d, r, n, void 0));
				return;
			}
		}
		for (c in n) n.hasOwnProperty(c) && (r = n[c], r != null && $(e, t, c, r, n, null));
	}
	var rp = {};
	function ip(e, t, n, r) {
		switch (t) {
			case "div":
			case "span":
			case "svg":
			case "path":
			case "a":
			case "g":
			case "p":
			case "li": break;
			case "input":
				var i = null, a = null, o = null, c = null, l = null, u = null, d = null;
				for (m in n) {
					var f = n[m];
					if (n.hasOwnProperty(m) && f != null) switch (m) {
						case "checked": break;
						case "value": break;
						case "defaultValue": l = f;
						default: r.hasOwnProperty(m) || $(e, t, m, null, r, f);
					}
				}
				for (var p in r) {
					var m = r[p];
					if (f = n[p], r.hasOwnProperty(p) && (m != null || f != null)) switch (p) {
						case "type":
							m !== f && (I = !0), a = m;
							break;
						case "name":
							m !== f && (I = !0), i = m;
							break;
						case "checked":
							m !== f && (I = !0), u = m;
							break;
						case "defaultChecked":
							m !== f && (I = !0), d = m;
							break;
						case "value":
							m !== f && (I = !0), o = m;
							break;
						case "defaultValue":
							m !== f && (I = !0), c = m;
							break;
						case "children":
						case "dangerouslySetInnerHTML":
							if (m != null) throw Error(s(137, t));
							break;
						default: m !== f && $(e, t, p, m, r, f);
					}
				}
				an(e, o, c, l, u, d, a, i);
				return;
			case "select":
				for (a in m = o = c = p = null, n) if (l = n[a], n.hasOwnProperty(a) && l != null) switch (a) {
					case "value": break;
					case "multiple": m = l;
					default: r.hasOwnProperty(a) || $(e, t, a, null, r, l);
				}
				for (i in r) if (a = r[i], l = n[i], r.hasOwnProperty(i) && (a != null || l != null)) switch (i) {
					case "value":
						a !== l && (I = !0), p = a;
						break;
					case "defaultValue":
						a !== l && (I = !0), c = a;
						break;
					case "multiple": a !== l && (I = !0), o = a;
					default: a !== l && $(e, t, i, a, r, l);
				}
				t = c, n = o, r = m, p == null ? !!r != !!n && (t == null ? cn(e, !!n, n ? [] : "", !1) : cn(e, !!n, t, !0)) : cn(e, !!n, p, !1);
				return;
			case "textarea":
				for (c in m = p = null, n) if (i = n[c], n.hasOwnProperty(c) && i != null && !r.hasOwnProperty(c)) switch (c) {
					case "value": break;
					case "children": break;
					default: $(e, t, c, null, r, i);
				}
				for (o in r) if (i = r[o], a = n[o], r.hasOwnProperty(o) && (i != null || a != null)) switch (o) {
					case "value":
						i !== a && (I = !0), p = i;
						break;
					case "defaultValue":
						i !== a && (I = !0), m = i;
						break;
					case "children": break;
					case "dangerouslySetInnerHTML":
						if (i != null) throw Error(s(91));
						break;
					default: i !== a && $(e, t, o, i, r, a);
				}
				ln(e, p, m);
				return;
			case "option":
				for (var h in n) if (p = n[h], n.hasOwnProperty(h) && p != null && !r.hasOwnProperty(h)) switch (h) {
					case "selected":
						e.selected = !1;
						break;
					default: $(e, t, h, null, r, p);
				}
				for (l in r) if (p = r[l], m = n[l], r.hasOwnProperty(l) && p !== m && (p != null || m != null)) switch (l) {
					case "selected":
						p !== m && (I = !0), e.selected = p && typeof p != "function" && typeof p != "symbol";
						break;
					default: $(e, t, l, p, r, m);
				}
				return;
			case "img":
			case "link":
			case "area":
			case "base":
			case "br":
			case "col":
			case "embed":
			case "hr":
			case "keygen":
			case "meta":
			case "param":
			case "source":
			case "track":
			case "wbr":
			case "menuitem":
				for (var g in n) p = n[g], n.hasOwnProperty(g) && p != null && !r.hasOwnProperty(g) && $(e, t, g, null, r, p);
				for (u in r) if (p = r[u], m = n[u], r.hasOwnProperty(u) && p !== m && (p != null || m != null)) switch (u) {
					case "children":
					case "dangerouslySetInnerHTML":
						if (p != null) throw Error(s(137, t));
						break;
					default: $(e, t, u, p, r, m);
				}
				return;
			default: if (mn(t)) {
				for (var _ in n) p = n[_], n.hasOwnProperty(_) && p !== void 0 && !r.hasOwnProperty(_) && tp(e, t, _, void 0, r, p);
				for (d in r) p = r[d], m = n[d], !r.hasOwnProperty(d) || p === m || p === void 0 && m === void 0 || tp(e, t, d, p, r, m);
				return;
			}
		}
		for (var v in n) p = n[v], n.hasOwnProperty(v) && p != null && !r.hasOwnProperty(v) && $(e, t, v, null, r, p);
		for (f in r) p = r[f], m = n[f], !r.hasOwnProperty(f) || p === m || p == null && m == null || $(e, t, f, p, r, m);
	}
	function ap(e) {
		switch (e) {
			case "css":
			case "script":
			case "font":
			case "img":
			case "image":
			case "input":
			case "link": return !0;
			default: return !1;
		}
	}
	function op() {
		if (typeof performance.getEntriesByType == "function") {
			for (var e = 0, t = 0, n = performance.getEntriesByType("resource"), r = 0; r < n.length; r++) {
				var i = n[r], a = i.transferSize, o = i.initiatorType, s = i.duration;
				if (a && s && ap(o)) {
					for (o = 0, s = i.responseEnd, r += 1; r < n.length; r++) {
						var c = n[r], l = c.startTime;
						if (l > s) break;
						var u = c.transferSize, d = c.initiatorType;
						u && ap(d) && (c = c.responseEnd, o += u * (c < s ? 1 : (s - l) / (c - l)));
					}
					if (--r, t += 8 * (a + o) / (i.duration / 1e3), e++, 10 < e) break;
				}
			}
			if (0 < e) return t / e / 1e6;
		}
		return navigator.connection && (e = navigator.connection.downlink, typeof e == "number") ? e : 5;
	}
	var sp = null, cp = null;
	function lp(e) {
		return e.nodeType === 9 ? e : e.ownerDocument;
	}
	function up(e) {
		switch (e) {
			case "http://www.w3.org/2000/svg": return 1;
			case "http://www.w3.org/1998/Math/MathML": return 2;
			default: return 0;
		}
	}
	function dp(e, t) {
		if (e === 0) switch (t) {
			case "svg": return 1;
			case "math": return 2;
			default: return 0;
		}
		return e === 1 && t === "foreignObject" ? 0 : e;
	}
	function fp(e, t, n, r) {
		return n = lp(n).createElement(e), n[F] = r, n[Et] = t, np(n, e, t), zt(n), n;
	}
	function pp(e, t) {
		return e === "textarea" || e === "noscript" || typeof t.children == "string" || typeof t.children == "number" || typeof t.children == "bigint" || typeof t.dangerouslySetInnerHTML == "object" && t.dangerouslySetInnerHTML !== null && t.dangerouslySetInnerHTML.__html != null;
	}
	var mp = null;
	function hp() {
		var e = window.event;
		return e && e.type === "popstate" ? e !== mp && (mp = e, !0) : (mp = null, !1);
	}
	var gp = typeof setTimeout == "function" ? setTimeout : void 0, _p = typeof clearTimeout == "function" ? clearTimeout : void 0, vp = typeof Promise == "function" ? Promise : void 0, yp = typeof requestAnimationFrame == "function" ? requestAnimationFrame : gp, bp = typeof queueMicrotask == "function" ? queueMicrotask : vp === void 0 ? gp : function(e) {
		return vp.resolve(null).then(e).catch(xp);
	};
	function xp(e) {
		setTimeout(function() {
			throw e;
		});
	}
	function Sp(e) {
		return e === "head";
	}
	function Cp(e, t) {
		var n = t, r = 0;
		do {
			var i = n.nextSibling;
			if (e.removeChild(n), i && i.nodeType === 8) {
				if (n = i.data, n === "/$" || n === "/&") {
					if (r === 0) {
						e.removeChild(i), Hh(t);
						return;
					}
					r--;
				} else if (n === "$" || n === "$?" || n === "$~" || n === "$!" || n === "&") r++;
				else if (n === "html") _m(e.ownerDocument.documentElement);
				else if (n === "head") {
					n = e.ownerDocument.head, _m(n);
					for (var a = n.firstChild; a;) {
						var o = a.nextSibling, s = a.nodeName;
						a[Mt] || s === "SCRIPT" || s === "STYLE" || s === "LINK" && a.rel.toLowerCase() === "stylesheet" || n.removeChild(a), a = o;
					}
				} else n === "body" && _m(e.ownerDocument.body);
			}
			n = i;
		} while (n);
		Hh(t);
	}
	function wp(e, t) {
		var n = e;
		e = 0;
		do {
			var r = n.nextSibling;
			if (n.nodeType === 1 ? t ? (n._stashedDisplay = n.style.display, n.style.display = "none") : (n.style.display = n._stashedDisplay || "", n.getAttribute("style") === "" && n.removeAttribute("style")) : n.nodeType === 3 && (t ? (n._stashedText = n.nodeValue, n.nodeValue = "") : n.nodeValue = n._stashedText || ""), r && r.nodeType === 8) {
				if (n = r.data, n === "/$") {
					if (e === 0) break;
					e--;
				} else n !== "$" && n !== "$?" && n !== "$~" && n !== "$!" || e++;
			}
			n = r;
		} while (n);
	}
	function Tp(e, t, n) {
		if (t = CSS.escape(t) === t ? t : "r-" + btoa(t).replace(/=/g, ""), e.style.viewTransitionName = t, n != null && (e.style.viewTransitionClass = n), n = getComputedStyle(e), n.display === "inline") {
			if (t = e.getClientRects(), t.length === 1) var r = 1;
			else for (var i = r = 0; i < t.length; i++) {
				var a = t[i];
				0 < a.width && 0 < a.height && r++;
			}
			r === 1 && (e = e.style, e.display = t.length === 1 ? "inline-block" : "block", e.marginTop = "-" + n.paddingTop, e.marginBottom = "-" + n.paddingBottom);
		}
	}
	function Ep(e, t) {
		e = e.style, t = t.style;
		var n = t == null ? null : t.hasOwnProperty("viewTransitionName") ? t.viewTransitionName : t.hasOwnProperty("view-transition-name") ? t["view-transition-name"] : null;
		e.viewTransitionName = n == null || typeof n == "boolean" ? "" : ("" + n).trim(), n = t == null ? null : t.hasOwnProperty("viewTransitionClass") ? t.viewTransitionClass : t.hasOwnProperty("view-transition-class") ? t["view-transition-class"] : null, e.viewTransitionClass = n == null || typeof n == "boolean" ? "" : ("" + n).trim(), e.display === "inline-block" && (t == null ? e.display = e.margin = "" : (n = t.display, e.display = n == null || typeof n == "boolean" ? "" : n, n = t.margin, n == null ? (n = t.hasOwnProperty("marginTop") ? t.marginTop : t["margin-top"], e.marginTop = n == null || typeof n == "boolean" ? "" : n, t = t.hasOwnProperty("marginBottom") ? t.marginBottom : t["margin-bottom"], e.marginBottom = t == null || typeof t == "boolean" ? "" : t) : e.margin = n));
	}
	function Dp(e, t, n) {
		return n = n.ownerDocument.defaultView, {
			rect: e,
			abs: t.position === "absolute" || t.position === "fixed",
			clip: t.clipPath !== "none" || t.overflow !== "visible" || t.filter !== "none" || t.mask !== "none" || t.mask !== "none" || t.borderRadius !== "0px",
			view: 0 <= e.bottom && 0 <= e.right && e.top <= n.innerHeight && e.left <= n.innerWidth
		};
	}
	function Op(e) {
		return Dp(e.getBoundingClientRect(), getComputedStyle(e), e);
	}
	function kp(e) {
		var t = e.getBoundingClientRect();
		t = new DOMRect(t.x + 2e4, t.y + 2e4, t.width, t.height);
		var n = getComputedStyle(e);
		return Dp(t, n, e);
	}
	function Ap(e) {
		return e.documentElement.clientHeight;
	}
	function jp(e) {
		this.addEventListener("load", e), this.addEventListener("error", e);
	}
	function Mp(e, t, n, r, i, a, o, s, c) {
		var l = t.nodeType === 9 ? t : t.ownerDocument;
		try {
			var u = l.startViewTransition({
				update: function() {
					var t = l.defaultView, n = t.navigation && t.navigation.transition, o = l.fonts.status;
					r();
					var s = [];
					if (o === "loaded" && (Ap(l), l.fonts.status === "loading" && s.push(l.fonts.ready)), o = s.length, e !== null) for (var c = e.suspenseyImages, u = 0, d = 0; d < c.length; d++) {
						var f = c[d];
						if (!f.complete) {
							var p = f.getBoundingClientRect();
							if (0 < p.bottom && 0 < p.right && p.top < t.innerHeight && p.left < t.innerWidth) {
								if (u += Xm(f), u > $m) {
									s.length = o;
									break;
								}
								f = new Promise(jp.bind(f)), s.push(f);
							}
						}
					}
					if (0 < s.length) return t = Promise.race([Promise.all(s), new Promise(function(e) {
						return setTimeout(e, 500);
					})]).then(i, i), (n ? Promise.allSettled([n.finished, t]) : t).then(a, a);
					if (i(), n) return n.finished.then(a, a);
					a();
				},
				types: n
			});
			l.__reactViewTransition = u;
			var d = [];
			return u.ready.then(function() {
				for (var e = l.documentElement.getAnimations({ subtree: !0 }), t = 0; t < e.length; t++) {
					var n = e[t], r = n.effect, i = r.pseudoElement;
					if (i != null && i.startsWith("::view-transition")) {
						d.push(n), n = r.getKeyframes();
						for (var a = i = void 0, s = !0, c = 0; c < n.length; c++) {
							var u = n[c], f = u.width;
							if (i === void 0) i = f;
							else if (i !== f) {
								s = !1;
								break;
							}
							if (f = u.height, a === void 0) a = f;
							else if (a !== f) {
								s = !1;
								break;
							}
							delete u.width, delete u.height, u.transform === "none" && delete u.transform;
						}
						s && i !== void 0 && a !== void 0 && (r.setKeyframes(n), s = getComputedStyle(r.target, r.pseudoElement), s.width !== i || s.height !== a) && (s = n[0], s.width = i, s.height = a, s = n[n.length - 1], s.width = i, s.height = a, r.setKeyframes(n));
					}
				}
				o();
			}, function(e) {
				l.__reactViewTransition === u && (l.__reactViewTransition = null);
				try {
					if (typeof e == "object" && e) switch (e.name) {
						case "InvalidStateError": (e.message === "View transition was skipped because document visibility state is hidden." || e.message === "Skipping view transition because document visibility state has become hidden." || e.message === "Skipping view transition because viewport size changed." || e.message === "Transition was aborted because of invalid state") && (e = null);
					}
					e !== null && c(e);
				} finally {
					r(), i(), o();
				}
			}), u.finished.finally(function() {
				for (var e = 0; e < d.length; e++) d[e].cancel();
				l.__reactViewTransition === u && (l.__reactViewTransition = null), s();
			}), u;
		} catch {
			return r(), i(), o(), null;
		}
	}
	function Np(e, t) {
		this._scope = document.documentElement, this._selector = "::view-transition-" + e + "(" + t + ")";
	}
	Np.prototype.animate = function(e, t) {
		return t = typeof t == "number" ? { duration: t } : T({}, t), t.pseudoElement = this._selector, this._scope.animate(e, t);
	}, Np.prototype.getAnimations = function() {
		for (var e = this._scope, t = this._selector, n = e.getAnimations({ subtree: !0 }), r = [], i = 0; i < n.length; i++) {
			var a = n[i].effect;
			a !== null && a.target === e && a.pseudoElement === t && r.push(n[i]);
		}
		return r;
	}, Np.prototype.getComputedStyle = function() {
		return getComputedStyle(this._scope, this._selector);
	};
	function Pp(e) {
		return {
			name: e,
			group: new Np("group", e),
			imagePair: new Np("image-pair", e),
			old: new Np("old", e),
			new: new Np("new", e)
		};
	}
	function Fp(e) {
		this._fragmentFiber = e, this._observers = this._eventListeners = null;
	}
	Fp.prototype.addEventListener = function(e, t, n) {
		var r = null, i = null;
		if (!(n != null && typeof n != "boolean" && (r = n.signal || null, r !== null && r.aborted))) {
			this._eventListeners === null && (this._eventListeners = []);
			var a = this._eventListeners;
			if (Bp(a, e, t, n) === -1) {
				var o = this, s = t;
				n != null && typeof n != "boolean" && !0 === n.once && (s = function(r) {
					o.removeEventListener(e, t, n), typeof t == "function" ? t.call(this, r) : t.handleEvent(r);
				}), r !== null && (i = o.removeEventListener.bind(o, e, t, n), r.addEventListener("abort", i, { once: !0 }), i = r.removeEventListener.bind(r, "abort", i)), r = Rp(n), a.push({
					type: e,
					listener: t,
					optionsOrUseCapture: n,
					attachedListener: s,
					cleanup: i
				}), h(this._fragmentFiber.child, !1, Ip, e, s, r);
			}
			this._eventListeners = a;
		}
	};
	function Ip(e, t, n, r) {
		return b(e).addEventListener(t, n, r), !1;
	}
	Fp.prototype.removeEventListener = function(e, t, n) {
		var r = this._eventListeners;
		if (r !== null && (t = Bp(r, e, t, n), t !== -1)) {
			var i = r[t];
			n = i.attachedListener;
			var a = i.cleanup;
			i = Rp(i.optionsOrUseCapture), h(this._fragmentFiber.child, !1, Lp, e, n, i), r.splice(t, 1), a !== null && a();
		}
	};
	function Lp(e, t, n, r) {
		return b(e).removeEventListener(t, n, r), !1;
	}
	function Rp(e) {
		return e != null && typeof e != "boolean" && (!0 === e.once || e.signal instanceof AbortSignal) ? {
			capture: e.capture,
			passive: e.passive
		} : e;
	}
	function zp(e) {
		return e == null ? "c=0" : typeof e == "boolean" ? "c=" + (e ? "1" : "0") : "c=" + (e.capture ? "1" : "0");
	}
	function Bp(e, t, n, r) {
		if (e.length === 0) return -1;
		r = zp(r);
		for (var i = 0; i < e.length; i++) {
			var a = e[i];
			if (a.type === t && a.listener === n && zp(a.optionsOrUseCapture) === r) return i;
		}
		return -1;
	}
	Fp.prototype.dispatchEvent = function(e) {
		var t = g(this._fragmentFiber);
		if (t === null) return !0;
		t = b(t);
		var n = this._eventListeners;
		if (n !== null && 0 < n.length || !e.bubbles) {
			var r = t.nodeType === 9 ? t.createComment("") : document.createTextNode("");
			if (n) for (var i = 0; i < n.length; i++) {
				var a = n[i];
				r.addEventListener(a.type, a.attachedListener, Rp(a.optionsOrUseCapture));
			}
			if (t.appendChild(r), e = r.dispatchEvent(e), n) for (i = 0; i < n.length; i++) a = n[i], r.removeEventListener(a.type, a.attachedListener, Rp(a.optionsOrUseCapture));
			return t.removeChild(r), e;
		}
		return t.dispatchEvent(e);
	}, Fp.prototype.focus = function(e) {
		h(this._fragmentFiber.child, !0, Vp, e, void 0, void 0);
	};
	function Vp(e, t) {
		return e.tag !== 6 && (e = b(e), pm(e, t));
	}
	Fp.prototype.focusLast = function(e) {
		var t = [];
		h(this._fragmentFiber.child, !0, Hp, t, void 0, void 0);
		for (var n = t.length - 1; 0 <= n && !Vp(t[n], e); n--);
	};
	function Hp(e, t) {
		return t.push(e), !1;
	}
	Fp.prototype.blur = function() {
		var e = g(this._fragmentFiber);
		e !== null && (e = b(e), e = lp(e).activeElement, e !== null && h(this._fragmentFiber.child, !1, Up, e, void 0, void 0));
	};
	function Up(e, t) {
		return e.tag !== 6 && (e = b(e), e === t || e.contains(t) ? (t.blur(), !0) : !1);
	}
	Fp.prototype.observeUsing = function(e) {
		this._observers === null && (this._observers = /* @__PURE__ */ new Set()), this._observers.add(e), h(this._fragmentFiber.child, !1, Wp, e, void 0, void 0);
	};
	function Wp(e, t) {
		return e.tag === 6 || (e = b(e), t.observe(e)), !1;
	}
	Fp.prototype.unobserveUsing = function(e) {
		var t = this._observers;
		if (t !== null && t.has(e)) {
			t.delete(e), h(this._fragmentFiber.child, !1, Gp, e, void 0, void 0);
			for (var n = t = 0; n < Kp.length; n++) {
				var r = Kp[n];
				r.fragmentInstance === this && r.observer === e ? e.unobserve(r.instance) : Kp[t++] = r;
			}
			Kp.length = t;
		}
	};
	function Gp(e, t) {
		return e.tag === 6 || (e = b(e), t.unobserve(e)), !1;
	}
	var Kp = [], qp = !1;
	function Jp(e, t, n) {
		Kp.push({
			fragmentInstance: e,
			observer: t,
			instance: n
		}), qp || (qp = !0, mm(function() {
			qp = !1;
			var e = Kp;
			Kp = [];
			for (var t = 0; t < e.length; t++) {
				var n = e[t];
				n.observer.unobserve(n.instance);
			}
		}));
	}
	Fp.prototype.getClientRects = function() {
		var e = [];
		return h(this._fragmentFiber.child, !1, Yp, e, void 0, void 0), e;
	};
	function Yp(e, t) {
		if (e.tag === 6) {
			e = e.stateNode;
			var n = e.ownerDocument.createRange();
			n.selectNodeContents(e), t.push.apply(t, n.getClientRects());
		} else e = b(e), t.push.apply(t, e.getClientRects());
		return !1;
	}
	Fp.prototype.getRootNode = function(e) {
		var t = g(this._fragmentFiber);
		return t === null ? this : b(t).getRootNode(e);
	}, Fp.prototype.compareDocumentPosition = function(e) {
		var t = g(this._fragmentFiber);
		if (t === null) return Node.DOCUMENT_POSITION_DISCONNECTED;
		var n = [];
		h(this._fragmentFiber.child, !1, Hp, n, void 0, void 0);
		var r = b(t);
		if (n.length === 0) {
			if (n = r, _(this._fragmentFiber)) {
				a: {
					for (t = this._fragmentFiber.return; t !== null;) {
						if (t.tag === 4) {
							t = t.stateNode.containerInfo;
							break a;
						}
						if (t.tag === 3 || t.tag === 5 || t.tag === 27) break;
						t = t.return;
					}
					t = null;
				}
				t != null && (n = t);
			}
			t = this._fragmentFiber;
			var i = r = n.compareDocumentPosition(e);
			return n === e ? i = Node.DOCUMENT_POSITION_CONTAINS : r & Node.DOCUMENT_POSITION_CONTAINED_BY && (n = v(t)[1], n === null ? i = Node.DOCUMENT_POSITION_PRECEDING : (e = b(n).compareDocumentPosition(e), i = e === 0 || e & Node.DOCUMENT_POSITION_FOLLOWING ? Node.DOCUMENT_POSITION_FOLLOWING : Node.DOCUMENT_POSITION_PRECEDING)), i |= Node.DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC;
		}
		t = b(n[0]), i = b(n[n.length - 1]);
		var a = _(this._fragmentFiber) ? t.parentElement : r;
		if (a == null) return Node.DOCUMENT_POSITION_DISCONNECTED;
		r = a.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_CONTAINED_BY, a = a.compareDocumentPosition(i) & Node.DOCUMENT_POSITION_CONTAINED_BY;
		var o = t.compareDocumentPosition(e), s = i.compareDocumentPosition(e), c = o & Node.DOCUMENT_POSITION_CONTAINED_BY || s & Node.DOCUMENT_POSITION_CONTAINED_BY;
		return s = r && a && o & Node.DOCUMENT_POSITION_FOLLOWING && s & Node.DOCUMENT_POSITION_PRECEDING, t = r && t === e || a && i === e || c || s ? Node.DOCUMENT_POSITION_CONTAINED_BY : !r && t === e || !a && i === e ? Node.DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC : o, t & Node.DOCUMENT_POSITION_DISCONNECTED || t & Node.DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC || Xp(t, this._fragmentFiber, n[0], n[n.length - 1], e) ? t : Node.DOCUMENT_POSITION_IMPLEMENTATION_SPECIFIC;
	};
	function Xp(e, t, n, r, i) {
		var a = Ft(i);
		if (e & Node.DOCUMENT_POSITION_CONTAINED_BY) {
			if (n = !!a) a: {
				for (; a !== null;) {
					if (a.tag === 7 && (a === t || a.alternate === t)) {
						n = !0;
						break a;
					}
					a = a.return;
				}
				n = !1;
			}
			return n;
		}
		if (e & Node.DOCUMENT_POSITION_CONTAINS) {
			if (a === null) return a = i.ownerDocument, i === a || i === a.documentElement || i === a.body;
			a: {
				for (a = t, t = g(t); a !== null;) {
					if (!(a.tag !== 5 && a.tag !== 3 && a.tag !== 27 || a !== t && a.alternate !== t)) {
						a = !0;
						break a;
					}
					a = a.return;
				}
				a = !1;
			}
			return a;
		}
		return e & Node.DOCUMENT_POSITION_PRECEDING ? ((t = !!a) && !(t = a === n) && (t = w(n, a, C), t === null ? t = !1 : (h(t, !0, te, a, n), a = ee, ee = null, t = a !== null)), t) : e & Node.DOCUMENT_POSITION_FOLLOWING ? ((t = !!a) && !(t = a === r) && (t = w(r, a, C), t === null ? t = !1 : (h(t, !0, S, a, r), a = ee, x = ee = null, t = a !== null)), t) : !1;
	}
	function Zp(e, t) {
		var n = e.ownerDocument.createRange();
		n.selectNodeContents(e), e = n.getBoundingClientRect(), window.scrollTo(window.scrollX + e.left, t ? window.scrollY + e.top : window.scrollY + e.bottom - window.innerHeight);
	}
	Fp.prototype.scrollIntoView = function(e) {
		if (typeof e == "object") throw Error(s(566));
		var t = [];
		h(this._fragmentFiber.child, !1, Hp, t, void 0, void 0);
		var n = !1 !== e;
		if (t.length === 0) {
			var r = v(this._fragmentFiber);
			if (r = n ? r[1] || r[0] || g(this._fragmentFiber) : r[0] || r[1], r === null) return;
			if (r.tag === 6) {
				e = b(r), Zp(e, n);
				return;
			}
			if (r = b(r), r.nodeType !== 9) {
				if (r.nodeType === 11) {
					n = "host" in r ? r.host : null, n !== null && n.scrollIntoView(e);
					return;
				}
				r.scrollIntoView(e);
			}
		}
		for (r = n ? t.length - 1 : 0; r !== (n ? -1 : t.length);) {
			var i = t[r];
			i.tag === 6 ? (i = b(i), Zp(i, n)) : b(i).scrollIntoView(e), r += n ? -1 : 1;
		}
	};
	function Qp(e, t) {
		return e = b(e), $p(e, t), !1;
	}
	function $p(e, t) {
		e.reactFragments ??= /* @__PURE__ */ new Set(), e.reactFragments.add(t);
	}
	function em(e, t) {
		var n = t._eventListeners;
		if (n !== null) for (var r = 0; r < n.length; r++) {
			var i = n[r];
			e.addEventListener(i.type, i.attachedListener, Rp(i.optionsOrUseCapture));
		}
		e.nodeType !== 3 && (n = t._observers, n !== null && n.forEach(function(n) {
			for (var r = 0, i = 0; i < Kp.length; i++) {
				var a = Kp[i];
				(a.fragmentInstance !== t || a.observer !== n || a.instance !== e) && (Kp[r++] = a);
			}
			Kp.length = r, n.observe(e);
		}), $p(e, t));
	}
	function tm(e, t) {
		var n = t._eventListeners;
		if (n !== null) for (var r = 0; r < n.length; r++) {
			var i = n[r];
			e.removeEventListener(i.type, i.attachedListener, Rp(i.optionsOrUseCapture));
		}
		e.nodeType !== 3 && (n = t._observers, n !== null && n.forEach(function(n) {
			typeof n.rootMargin == "string" ? Jp(t, n, e) : n.unobserve(e);
		}), e.reactFragments != null && e.reactFragments.delete(t));
	}
	function nm(e) {
		var t = e.firstChild;
		for (t && t.nodeType === 10 && (t = t.nextSibling); t;) {
			var n = t;
			switch (t = t.nextSibling, n.nodeName) {
				case "HTML":
				case "HEAD":
				case "BODY":
					nm(n), Pt(n);
					continue;
				case "SCRIPT":
				case "STYLE": continue;
				case "LINK": if (n.rel.toLowerCase() === "stylesheet") continue;
			}
			e.removeChild(n);
		}
	}
	function rm(e, t, n, r) {
		for (; e.nodeType === 1;) {
			var i = n;
			if (e.nodeName.toLowerCase() !== t.toLowerCase()) {
				if (!r && (e.nodeName !== "INPUT" || e.type !== "hidden")) break;
			} else if (!r) {
				if (t === "input" && e.type === "hidden") {
					var a = i.name == null ? null : "" + i.name;
					if (i.type === "hidden" && e.getAttribute("name") === a) return e;
				} else return e;
			} else if (!e[Mt]) switch (t) {
				case "meta":
					if (!e.hasAttribute("itemprop")) break;
					return e;
				case "link":
					if (a = e.getAttribute("rel"), a === "stylesheet" && e.hasAttribute("data-precedence") || a !== i.rel || e.getAttribute("href") !== (i.href == null || i.href === "" ? null : i.href) || e.getAttribute("crossorigin") !== (i.crossOrigin == null ? null : i.crossOrigin) || e.getAttribute("title") !== (i.title == null ? null : i.title)) break;
					return e;
				case "style":
					if (e.hasAttribute("data-precedence")) break;
					return e;
				case "script":
					if (a = e.getAttribute("src"), (a !== (i.src == null ? null : i.src) || e.getAttribute("type") !== (i.type == null ? null : i.type) || e.getAttribute("crossorigin") !== (i.crossOrigin == null ? null : i.crossOrigin)) && a && e.hasAttribute("async") && !e.hasAttribute("itemprop")) break;
					return e;
				default: return e;
			}
			if (e = lm(e.nextSibling), e === null) break;
		}
		return null;
	}
	function im(e, t, n) {
		if (t === "") return null;
		for (; e.nodeType !== 3;) if ((e.nodeType !== 1 || e.nodeName !== "INPUT" || e.type !== "hidden") && !n || (e = lm(e.nextSibling), e === null)) return null;
		return e;
	}
	function am(e, t) {
		for (; e.nodeType !== 8;) if ((e.nodeType !== 1 || e.nodeName !== "INPUT" || e.type !== "hidden") && !t || (e = lm(e.nextSibling), e === null)) return null;
		return e;
	}
	function om(e) {
		return e.data === "$?" || e.data === "$~";
	}
	function sm(e) {
		return e.data === "$!" || e.data === "$?" && e.ownerDocument.readyState !== "loading";
	}
	function cm(e, t) {
		var n = e.ownerDocument;
		if (e.data === "$~") e._reactRetry = t;
		else if (e.data !== "$?" || n.readyState !== "loading") t();
		else {
			var r = function() {
				t(), n.removeEventListener("DOMContentLoaded", r);
			};
			n.addEventListener("DOMContentLoaded", r), e._reactRetry = r;
		}
	}
	function lm(e) {
		for (; e != null; e = e.nextSibling) {
			var t = e.nodeType;
			if (t === 1 || t === 3) break;
			if (t === 8) {
				if (t = e.data, t === "$" || t === "$!" || t === "$?" || t === "$~" || t === "&" || t === "F!" || t === "F") break;
				if (t === "/$" || t === "/&") return null;
			}
		}
		return e;
	}
	var um = null;
	function dm(e) {
		e = e.nextSibling;
		for (var t = 0; e;) {
			if (e.nodeType === 8) {
				var n = e.data;
				if (n === "/$" || n === "/&") {
					if (t === 0) return lm(e.nextSibling);
					t--;
				} else n !== "$" && n !== "$!" && n !== "$?" && n !== "$~" && n !== "&" || t++;
			}
			e = e.nextSibling;
		}
		return null;
	}
	function fm(e) {
		e = e.previousSibling;
		for (var t = 0; e;) {
			if (e.nodeType === 8) {
				var n = e.data;
				if (n === "$" || n === "$!" || n === "$?" || n === "$~" || n === "&") {
					if (t === 0) return e;
					t--;
				} else n !== "/$" && n !== "/&" || t++;
			}
			e = e.previousSibling;
		}
		return null;
	}
	function pm(e, t) {
		function n() {
			r = !0;
		}
		if (e.ownerDocument.activeElement === e) return !0;
		var r = !1;
		try {
			e.ownerDocument.addEventListener("focus", n, !0), (e.focus || HTMLElement.prototype.focus).call(e, t);
		} finally {
			e.ownerDocument.removeEventListener("focus", n, !0);
		}
		return r;
	}
	function mm(e) {
		yp(function() {
			yp(function(t) {
				return e(t);
			});
		});
	}
	function hm(e, t, n) {
		switch (t = lp(n), e) {
			case "html":
				if (e = t.documentElement, !e) throw Error(s(452));
				return e;
			case "head":
				if (e = t.head, !e) throw Error(s(453));
				return e;
			case "body":
				if (e = t.body, !e) throw Error(s(454));
				return e;
			default: throw Error(s(451));
		}
	}
	function gm(e, t, n) {
		for (var r in n) {
			var i = n[r];
			n.hasOwnProperty(r) && i != null && $(e, t, r, null, rp, i);
		}
		n.dangerouslySetInnerHTML != null && (e.textContent = ""), e.onclick === vn && (e.onclick = null), Pt(e);
	}
	function _m(e) {
		for (var t = e.attributes; t.length;) e.removeAttributeNode(t[0]);
		Pt(e);
	}
	var vm = /* @__PURE__ */ new Map(), ym = /* @__PURE__ */ new Set();
	function bm(e) {
		if (typeof e.getRootNode == "function") {
			var t = e.getRootNode();
			if (t.nodeType === 9 || t.nodeType === 11) return t;
		}
		return e.nodeType === 9 ? e : e.ownerDocument;
	}
	var xm = A.d;
	A.d = {
		f: Sm,
		r: Cm,
		D: Em,
		C: Dm,
		L: Om,
		m: km,
		X: jm,
		S: Am,
		M: Mm
	};
	function Sm() {
		var e = xm.f(), t = zd();
		return e || t;
	}
	function Cm(e) {
		var t = It(e);
		t !== null && t.tag === 5 && t.type === "form" ? nc(t) : xm.r(e);
	}
	var wm = typeof document > "u" ? null : document;
	function Tm(e, t, n) {
		var r = wm;
		if (r && typeof t == "string" && t) {
			var i = rn(t);
			i = "link[rel=\"" + e + "\"][href=\"" + i + "\"]", typeof n == "string" && (i += "[crossorigin=\"" + n + "\"]"), ym.has(i) || (ym.add(i), e = {
				rel: e,
				crossOrigin: n,
				href: t
			}, r.querySelector(i) === null && (t = r.createElement("link"), np(t, "link", e), zt(t), r.head.appendChild(t)));
		}
	}
	function Em(e) {
		xm.D(e), Tm("dns-prefetch", e, null);
	}
	function Dm(e, t) {
		xm.C(e, t), Tm("preconnect", e, t);
	}
	function Om(e, t, n) {
		xm.L(e, t, n);
		var r = wm;
		if (r && e && t) {
			var i = "link[rel=\"preload\"][as=\"" + rn(t) + "\"]";
			t === "image" && n && n.imageSrcSet ? (i += "[imagesrcset=\"" + rn(n.imageSrcSet) + "\"]", typeof n.imageSizes == "string" && (i += "[imagesizes=\"" + rn(n.imageSizes) + "\"]")) : i += "[href=\"" + rn(e) + "\"]";
			var a = i;
			switch (t) {
				case "style":
					a = Pm(e);
					break;
				case "script": a = Rm(e);
			}
			if (!(vm.has(a) || (e = T({
				rel: "preload",
				href: t === "image" && n && n.imageSrcSet ? void 0 : e,
				as: t
			}, n), vm.set(a, e), r.querySelector(i) !== null || t === "style" && r.querySelector(Fm(a)) || t === "script" && r.querySelector(zm(a))))) {
				var o = r.createElement("link");
				np(o, "link", e), t === "style" && (o[Nt] = !0, o.onload = o.onerror = function() {
					Bt(o);
				}), zt(o), r.head.appendChild(o);
			}
		}
	}
	function km(e, t) {
		xm.m(e, t);
		var n = wm;
		if (n && e) {
			var r = t && typeof t.as == "string" ? t.as : "script", i = "link[rel=\"modulepreload\"][as=\"" + rn(r) + "\"][href=\"" + rn(e) + "\"]", a = i;
			switch (r) {
				case "audioworklet":
				case "paintworklet":
				case "serviceworker":
				case "sharedworker":
				case "worker":
				case "script": a = Rm(e);
			}
			if (!vm.has(a) && (e = T({
				rel: "modulepreload",
				href: e
			}, t), vm.set(a, e), n.querySelector(i) === null)) {
				switch (r) {
					case "audioworklet":
					case "paintworklet":
					case "serviceworker":
					case "sharedworker":
					case "worker":
					case "script": if (n.querySelector(zm(a))) return;
				}
				r = n.createElement("link"), np(r, "link", e), zt(r), n.head.appendChild(r);
			}
		}
	}
	function Am(e, t, n) {
		xm.S(e, t, n);
		var r = wm;
		if (r && e) {
			var i = Rt(r).hoistableStyles, a = Pm(e);
			t ||= "default";
			var o = i.get(a);
			if (!o) {
				var s = {
					loading: 0,
					preload: null
				};
				if (o = r.querySelector(Fm(a))) s.loading = 5;
				else {
					e = T({
						rel: "stylesheet",
						href: e,
						"data-precedence": t
					}, n), (n = vm.get(a)) && Hm(e, n);
					var c = o = r.createElement("link");
					zt(c), np(c, "link", e), c._p = new Promise(function(e, t) {
						c.onload = e, c.onerror = t;
					}), c.addEventListener("load", function() {
						s.loading |= 1;
					}), c.addEventListener("error", function() {
						s.loading |= 2;
					}), s.loading |= 4, Vm(o, t, r);
				}
				o = {
					type: "stylesheet",
					instance: o,
					count: 1,
					state: s
				}, i.set(a, o);
			}
		}
	}
	function jm(e, t) {
		xm.X(e, t);
		var n = wm;
		if (n && e) {
			var r = Rt(n).hoistableScripts, i = Rm(e), a = r.get(i);
			a || (a = n.querySelector(zm(i)), a || (e = T({
				src: e,
				async: !0
			}, t), (t = vm.get(i)) && Um(e, t), a = n.createElement("script"), zt(a), np(a, "link", e), n.head.appendChild(a)), a = {
				type: "script",
				instance: a,
				count: 1,
				state: null
			}, r.set(i, a));
		}
	}
	function Mm(e, t) {
		xm.M(e, t);
		var n = wm;
		if (n && e) {
			var r = Rt(n).hoistableScripts, i = Rm(e), a = r.get(i);
			a || (a = n.querySelector(zm(i)), a || (e = T({
				src: e,
				async: !0,
				type: "module"
			}, t), (t = vm.get(i)) && Um(e, t), a = n.createElement("script"), zt(a), np(a, "link", e), n.head.appendChild(a)), a = {
				type: "script",
				instance: a,
				count: 1,
				state: null
			}, r.set(i, a));
		}
	}
	function Nm(e, t, n, r) {
		var i = (i = ke.current) ? bm(i) : null;
		if (!i) throw Error(s(446));
		switch (e) {
			case "meta":
			case "title": return null;
			case "style": return typeof n.precedence == "string" && typeof n.href == "string" ? (n = Pm(n.href), t = Rt(i).hoistableStyles, r = t.get(n), r || (r = {
				type: "style",
				instance: null,
				count: 0,
				state: null
			}, t.set(n, r)), r) : {
				type: "void",
				instance: null,
				count: 0,
				state: null
			};
			case "link":
				if (n.rel === "stylesheet" && typeof n.href == "string" && typeof n.precedence == "string") {
					e = Pm(n.href);
					var a = Rt(i).hoistableStyles, o = a.get(e);
					if (o || (i = i.ownerDocument || i, o = {
						type: "stylesheet",
						instance: null,
						count: 0,
						state: {
							loading: 0,
							preload: null
						}
					}, a.set(e, o), (a = i.querySelector(Fm(e))) ? a._p || (o.instance = a, o.state.loading = 5) : (a = vm.get(e), a || (a = {
						rel: "preload",
						as: "style",
						href: n.href,
						crossOrigin: n.crossOrigin,
						integrity: n.integrity,
						media: n.media,
						hrefLang: n.hrefLang,
						referrerPolicy: n.referrerPolicy
					}, vm.set(e, a)), Lm(i, e, a, o.state))), t && r === null) throw Error(s(528, ""));
					return o;
				}
				if (t && r !== null) throw Error(s(529, ""));
				return null;
			case "script": return t = n.async, n = n.src, typeof n == "string" && t && typeof t != "function" && typeof t != "symbol" ? (n = Rm(n), t = Rt(i).hoistableScripts, r = t.get(n), r || (r = {
				type: "script",
				instance: null,
				count: 0,
				state: null
			}, t.set(n, r)), r) : {
				type: "void",
				instance: null,
				count: 0,
				state: null
			};
			default: throw Error(s(444, e));
		}
	}
	function Pm(e) {
		return "href=\"" + rn(e) + "\"";
	}
	function Fm(e) {
		return "link[rel=\"stylesheet\"][" + e + "]";
	}
	function Im(e) {
		return T({}, e, {
			"data-precedence": e.precedence,
			precedence: null
		});
	}
	function Lm(e, t, n, r) {
		if (t = e.querySelector("link[rel=\"preload\"][as=\"style\"][" + t + "]")) {
			if (!0 !== t[Nt]) {
				r.loading = 1;
				return;
			}
		} else t = e.createElement("link"), t[Nt] = !0, t.onload = t.onerror = Bt.bind(null, t), np(t, "link", n), zt(t), e.head.appendChild(t);
		r.preload = t, t.addEventListener("load", function() {
			return r.loading |= 1;
		}), t.addEventListener("error", function() {
			return r.loading |= 2;
		});
	}
	function Rm(e) {
		return "[src=\"" + rn(e) + "\"]";
	}
	function zm(e) {
		return "script[async]" + e;
	}
	function Bm(e, t, n) {
		if (t.count++, t.instance === null) switch (t.type) {
			case "style":
				var r = e.querySelector("style[data-href~=\"" + rn(n.href) + "\"]");
				if (r) return t.instance = r, zt(r), r;
				var i = T({}, n, {
					"data-href": n.href,
					"data-precedence": n.precedence,
					href: null,
					precedence: null
				});
				return r = (e.ownerDocument || e).createElement("style"), zt(r), np(r, "style", i), Vm(r, n.precedence, e), t.instance = r;
			case "stylesheet":
				i = Pm(n.href);
				var a = e.querySelector(Fm(i));
				if (a) return t.state.loading |= 4, t.instance = a, zt(a), a;
				r = Im(n), (i = vm.get(i)) && Hm(r, i), a = (e.ownerDocument || e).createElement("link"), zt(a);
				var o = a;
				return o._p = new Promise(function(e, t) {
					o.onload = e, o.onerror = t;
				}), np(a, "link", r), t.state.loading |= 4, Vm(a, n.precedence, e), t.instance = a;
			case "script": return a = Rm(n.src), (i = e.querySelector(zm(a))) ? (t.instance = i, zt(i), i) : (r = n, (i = vm.get(a)) && (r = T({}, n), Um(r, i)), e = e.ownerDocument || e, i = e.createElement("script"), zt(i), np(i, "link", r), e.head.appendChild(i), t.instance = i);
			case "void": return null;
			default: throw Error(s(443, t.type));
		}
		else t.type === "stylesheet" && !(t.state.loading & 4) && (r = t.instance, t.state.loading |= 4, Vm(r, n.precedence, e));
		return t.instance;
	}
	function Vm(e, t, n) {
		for (var r = n.querySelectorAll("link[rel=\"stylesheet\"][data-precedence],style[data-precedence]"), i = r.length ? r[r.length - 1] : null, a = i, o = 0; o < r.length; o++) {
			var s = r[o];
			if (s.dataset.precedence === t) a = s;
			else if (a !== i) break;
		}
		a ? a.parentNode.insertBefore(e, a.nextSibling) : (t = n.nodeType === 9 ? n.head : n, t.insertBefore(e, t.firstChild));
	}
	function Hm(e, t) {
		e.crossOrigin ??= t.crossOrigin, e.referrerPolicy ??= t.referrerPolicy, e.title ??= t.title;
	}
	function Um(e, t) {
		e.crossOrigin ??= t.crossOrigin, e.referrerPolicy ??= t.referrerPolicy, e.integrity ??= t.integrity;
	}
	var Wm = null;
	function Gm(e, t, n) {
		if (Wm === null) {
			var r = /* @__PURE__ */ new Map(), i = Wm = /* @__PURE__ */ new Map();
			i.set(n, r);
		} else i = Wm, r = i.get(n), r || (r = /* @__PURE__ */ new Map(), i.set(n, r));
		if (r.has(e)) return r;
		for (r.set(e, null), n = n.getElementsByTagName(e), i = 0; i < n.length; i++) {
			var a = n[i];
			if (!(a[Mt] || a[F] || e === "link" && a.getAttribute("rel") === "stylesheet") && a.namespaceURI !== "http://www.w3.org/2000/svg") {
				var o = a.getAttribute(t) || "";
				o = e + o;
				var s = r.get(o);
				s ? s.push(a) : r.set(o, [a]);
			}
		}
		return r;
	}
	function Km(e, t, n) {
		e = e.ownerDocument || e, e.head.insertBefore(n, t === "title" ? e.querySelector("head > title") : null);
	}
	function qm(e, t, n) {
		if (n === 1 || t.itemProp != null) return !1;
		switch (e) {
			case "meta":
			case "title": return !0;
			case "style":
				if (typeof t.precedence != "string" || typeof t.href != "string" || t.href === "") break;
				return !0;
			case "link":
				if (typeof t.rel != "string" || typeof t.href != "string" || t.href === "" || t.onLoad || t.onError) break;
				switch (t.rel) {
					case "stylesheet": return e = t.disabled, typeof t.precedence == "string" && e == null;
					default: return !0;
				}
			case "script": if (t.async && typeof t.async != "function" && typeof t.async != "symbol" && !t.onLoad && !t.onError && t.src && typeof t.src == "string") return !0;
		}
		return !1;
	}
	function Jm(e, t) {
		return e === "img" && t.src != null && t.src !== "" && t.onLoad == null && t.loading !== "lazy";
	}
	function Ym(e) {
		return !(e.type === "stylesheet" && !(e.state.loading & 3));
	}
	function Xm(e) {
		return (e.width || 100) * (e.height || 100) * (typeof devicePixelRatio == "number" ? devicePixelRatio : 1) * .25;
	}
	function Zm(e, t) {
		typeof t.decode == "function" && (e.imgCount++, t.complete || (e.imgBytes += Xm(t), e.suspenseyImages.push(t)), e = rh.bind(e), t.decode().then(e, e));
	}
	function Qm(e, t, n, r) {
		if (n.type === "stylesheet" && (typeof r.media != "string" || !1 !== matchMedia(r.media).matches) && !(n.state.loading & 4)) {
			if (n.instance === null) {
				var i = Pm(r.href), a = t.querySelector(Fm(i));
				if (a) {
					t = a._p, typeof t == "object" && t && typeof t.then == "function" && (e.count++, e = nh.bind(e), t.then(e, e)), n.state.loading |= 4, n.instance = a, zt(a);
					return;
				}
				a = t.ownerDocument || t, r = Im(r), (i = vm.get(i)) && Hm(r, i), a = a.createElement("link"), zt(a);
				var o = a;
				o._p = new Promise(function(e, t) {
					o.onload = e, o.onerror = t;
				}), np(a, "link", r), n.instance = a;
			}
			e.stylesheets === null && (e.stylesheets = /* @__PURE__ */ new Map()), e.stylesheets.set(n, t), (t = n.state.preload) && !(n.state.loading & 3) && (e.count++, n = nh.bind(e), t.addEventListener("load", n), t.addEventListener("error", n));
		}
	}
	var $m = 0;
	function eh(e, t) {
		return e.stylesheets && e.count === 0 && ah(e, e.stylesheets), 0 < e.count || 0 < e.imgCount ? function(n) {
			var r = setTimeout(function() {
				if (e.stylesheets && ah(e, e.stylesheets), e.unsuspend) {
					var t = e.unsuspend;
					e.unsuspend = null, t();
				}
			}, 6e4 + t);
			0 < e.imgBytes && $m === 0 && ($m = 62500 * op());
			var i = setTimeout(function() {
				if (e.waitingForImages = !1, e.count === 0 && (e.stylesheets && ah(e, e.stylesheets), e.unsuspend)) {
					var t = e.unsuspend;
					e.unsuspend = null, t();
				}
			}, (e.imgBytes > $m ? 50 : 800) + t);
			return e.unsuspend = n, function() {
				e.unsuspend = null, clearTimeout(r), clearTimeout(i);
			};
		} : null;
	}
	function th(e) {
		if (e.count === 0 && (e.imgCount === 0 || !e.waitingForImages)) {
			if (e.stylesheets) ah(e, e.stylesheets);
			else if (e.unsuspend) {
				var t = e.unsuspend;
				e.unsuspend = null, t();
			}
		}
	}
	function nh() {
		this.count--, th(this);
	}
	function rh() {
		this.imgCount--, th(this);
	}
	var ih = null;
	function ah(e, t) {
		e.stylesheets = null, e.unsuspend !== null && (e.count++, ih = /* @__PURE__ */ new Map(), t.forEach(oh, e), ih = null, nh.call(e));
	}
	function oh(e, t) {
		if (!(t.state.loading & 4)) {
			var n = ih.get(e);
			if (n) var r = n.get(null);
			else {
				n = /* @__PURE__ */ new Map(), ih.set(e, n);
				for (var i = e.querySelectorAll("link[data-precedence],style[data-precedence]"), a = 0; a < i.length; a++) {
					var o = i[a];
					(o.nodeName === "LINK" || o.getAttribute("media") !== "not all") && (n.set(o.dataset.precedence, o), r = o);
				}
				r && n.set(null, r);
			}
			i = t.instance, o = i.getAttribute("data-precedence"), a = n.get(o) || r, a === r && n.set(null, i), n.set(o, i), this.count++, r = nh.bind(this), i.addEventListener("load", r), i.addEventListener("error", r), a ? a.parentNode.insertBefore(i, a.nextSibling) : (e = e.nodeType === 9 ? e.head : e, e.insertBefore(i, e.firstChild)), t.state.loading |= 4;
		}
	}
	var sh = {
		$$typeof: D,
		Provider: null,
		Consumer: null,
		_currentValue: Se,
		_currentValue2: Se,
		_threadCount: 0
	};
	function ch(e, t, n, r, i, a, o, s, c) {
		this.tag = 1, this.containerInfo = e, this.pingCache = this.current = this.pendingChildren = null, this.timeoutHandle = -1, this.callbackNode = this.next = this.pendingContext = this.context = this.cancelPendingCommit = null, this.callbackPriority = 0, this.expirationTimes = ht(-1), this.entangledLanes = this.shellSuspendCounter = this.errorRecoveryDisabledLanes = this.expiredLanes = this.warmLanes = this.pingedLanes = this.suspendedLanes = this.pendingLanes = 0, this.entanglements = ht(0), this.hiddenUpdates = ht(null), this.identifierPrefix = r, this.onUncaughtError = i, this.onCaughtError = a, this.onRecoverableError = o, this.pooledCache = null, this.pooledCacheLanes = 0, this.formState = c, this.transitionTypes = null, this.incompleteTransitions = /* @__PURE__ */ new Map();
	}
	function lh(e, t, n, r, i, a, o, s, c, l, u, d) {
		return e = new ch(e, t, n, o, c, l, u, d, s), t = 1, !0 === a && (t |= 24), a = Mi(3, null, null, t), e.current = a, a.stateNode = e, t = ja(), t.refCount++, e.pooledCache = t, t.refCount++, a.memoizedState = {
			element: r,
			isDehydrated: n,
			cache: t
		}, mo(a), e;
	}
	function uh(e) {
		return e ? (e = Ai, e) : Ai;
	}
	function dh(e, t, n, r, i, a) {
		i = uh(i), r.context === null ? r.context = i : r.pendingContext = i, r = go(t), r.payload = { element: n }, a = a === void 0 ? null : a, a !== null && (r.callback = a), n = _o(e, r, t), n !== null && (Pd(n, e, t), vo(n, e, t));
	}
	function fh(e, t) {
		if (e = e.memoizedState, e !== null && e.dehydrated !== null) {
			var n = e.retryLane;
			e.retryLane = n !== 0 && n < t ? n : t;
		}
	}
	function ph(e, t) {
		fh(e, t), (e = e.alternate) && fh(e, t);
	}
	function mh(e) {
		if (e.tag === 13 || e.tag === 31) {
			var t = Di(e, 67108864);
			t !== null && Pd(t, e, 67108864), ph(e, 67108864);
		}
	}
	function hh(e) {
		if (e.tag === 13 || e.tag === 31) {
			var t = jd();
			t = xt(t);
			var n = Di(e, t);
			n !== null && Pd(n, e, t), ph(e, t);
		}
	}
	var gh = !0;
	function _h(e, t, n, r) {
		var i = k.T;
		k.T = null;
		var a = A.p;
		try {
			A.p = 2, yh(e, t, n, r);
		} finally {
			A.p = a, k.T = i;
		}
	}
	function vh(e, t, n, r) {
		var i = k.T;
		k.T = null;
		var a = A.p;
		try {
			A.p = 8, yh(e, t, n, r);
		} finally {
			A.p = a, k.T = i;
		}
	}
	function yh(e, t, n, r) {
		if (gh) {
			var i = bh(r);
			if (i === null) Kf(e, t, r, xh, n), Mh(e, r);
			else if (Ph(i, e, t, n, r)) r.stopPropagation();
			else if (Mh(e, r), t & 4 && -1 < jh.indexOf(e)) {
				for (; i !== null;) {
					var a = It(i);
					if (a !== null) switch (a.tag) {
						case 3:
							if (a = a.stateNode, a.current.memoizedState.isDehydrated) {
								var o = lt(a.pendingLanes);
								if (o !== 0) {
									var s = a;
									for (s.pendingLanes |= 2, s.entangledLanes |= 2; o;) {
										var c = 1 << 31 - rt(o);
										s.entanglements[1] |= c, o &= ~c;
									}
									Ef(a), !(K & 6) && (gd = Ge() + 500, Df(0, !1));
								}
							}
							break;
						case 31:
						case 13: s = Di(a, 2), s !== null && Pd(s, a, 2), zd(), ph(a, 2);
					}
					if (a = bh(r), a === null && Kf(e, t, r, xh, n), a === i) break;
					i = a;
				}
				i !== null && r.stopPropagation();
			} else Kf(e, t, r, null, n);
		}
	}
	function bh(e) {
		return e = bn(e), Sh(e);
	}
	var xh = null;
	function Sh(e) {
		if (xh = null, e = Ft(e), e !== null) {
			var t = l(e);
			if (t === null) e = null;
			else {
				var n = t.tag;
				if (n === 13) {
					if (e = u(t), e !== null) return e;
					e = null;
				} else if (n === 31) {
					if (e = d(t), e !== null) return e;
					e = null;
				} else if (n === 3) {
					if (t.stateNode.current.memoizedState.isDehydrated) return t.tag === 3 ? t.stateNode.containerInfo : null;
					e = null;
				} else t !== e && (e = null);
			}
		}
		return xh = e, null;
	}
	function Ch(e) {
		switch (e) {
			case "beforetoggle":
			case "cancel":
			case "click":
			case "close":
			case "contextmenu":
			case "copy":
			case "cut":
			case "auxclick":
			case "dblclick":
			case "dragend":
			case "dragstart":
			case "drop":
			case "focusin":
			case "focusout":
			case "input":
			case "invalid":
			case "keydown":
			case "keypress":
			case "keyup":
			case "mousedown":
			case "mouseup":
			case "paste":
			case "pause":
			case "play":
			case "pointercancel":
			case "pointerdown":
			case "pointerup":
			case "ratechange":
			case "reset":
			case "seeked":
			case "submit":
			case "toggle":
			case "touchcancel":
			case "touchend":
			case "touchstart":
			case "volumechange":
			case "change":
			case "selectionchange":
			case "textInput":
			case "compositionstart":
			case "compositionend":
			case "compositionupdate":
			case "beforeblur":
			case "afterblur":
			case "beforeinput":
			case "blur":
			case "fullscreenchange":
			case "fullscreenerror":
			case "focus":
			case "hashchange":
			case "popstate":
			case "select":
			case "selectstart": return 2;
			case "drag":
			case "dragenter":
			case "dragexit":
			case "dragleave":
			case "dragover":
			case "mousemove":
			case "mouseout":
			case "mouseover":
			case "pointermove":
			case "pointerout":
			case "pointerover":
			case "resize":
			case "scroll":
			case "touchmove":
			case "wheel":
			case "mouseenter":
			case "mouseleave":
			case "pointerenter":
			case "pointerleave": return 8;
			case "message": switch (Ke()) {
				case qe: return 2;
				case Je: return 8;
				case Ye:
				case Xe: return 32;
				case Ze: return 268435456;
				default: return 32;
			}
			default: return 32;
		}
	}
	var wh = !1, Th = null, Eh = null, Dh = null, Oh = /* @__PURE__ */ new Map(), kh = /* @__PURE__ */ new Map(), Ah = [], jh = "mousedown mouseup touchcancel touchend touchstart auxclick dblclick pointercancel pointerdown pointerup dragend dragstart drop compositionend compositionstart keydown keypress keyup input textInput copy cut paste click change contextmenu reset".split(" ");
	function Mh(e, t) {
		switch (e) {
			case "focusin":
			case "focusout":
				Th = null;
				break;
			case "dragenter":
			case "dragleave":
				Eh = null;
				break;
			case "mouseover":
			case "mouseout":
				Dh = null;
				break;
			case "pointerover":
			case "pointerout":
				Oh.delete(t.pointerId);
				break;
			case "gotpointercapture":
			case "lostpointercapture": kh.delete(t.pointerId);
		}
	}
	function Nh(e, t, n, r, i, a) {
		return e === null || e.nativeEvent !== a ? (e = {
			blockedOn: t,
			domEventName: n,
			eventSystemFlags: r,
			nativeEvent: a,
			targetContainers: [i]
		}, t !== null && (t = It(t), t !== null && mh(t)), e) : (e.eventSystemFlags |= r, t = e.targetContainers, i !== null && t.indexOf(i) === -1 && t.push(i), e);
	}
	function Ph(e, t, n, r, i) {
		switch (t) {
			case "focusin": return Th = Nh(Th, e, t, n, r, i), !0;
			case "dragenter": return Eh = Nh(Eh, e, t, n, r, i), !0;
			case "mouseover": return Dh = Nh(Dh, e, t, n, r, i), !0;
			case "pointerover":
				var a = i.pointerId;
				return Oh.set(a, Nh(Oh.get(a) || null, e, t, n, r, i)), !0;
			case "gotpointercapture": return a = i.pointerId, kh.set(a, Nh(kh.get(a) || null, e, t, n, r, i)), !0;
		}
		return !1;
	}
	function Fh(e) {
		var t = Ft(e.target);
		if (t !== null) {
			var n = l(t);
			if (n !== null) {
				if (t = n.tag, t === 13) {
					if (t = u(n), t !== null) {
						e.blockedOn = t, wt(e.priority, function() {
							hh(n);
						});
						return;
					}
				} else if (t === 31) {
					if (t = d(n), t !== null) {
						e.blockedOn = t, wt(e.priority, function() {
							hh(n);
						});
						return;
					}
				} else if (t === 3 && n.stateNode.current.memoizedState.isDehydrated) {
					e.blockedOn = n.tag === 3 ? n.stateNode.containerInfo : null;
					return;
				}
			}
		}
		e.blockedOn = null;
	}
	function Ih(e) {
		if (e.blockedOn !== null) return !1;
		for (var t = e.targetContainers; 0 < t.length;) {
			var n = bh(e.nativeEvent);
			if (n === null) {
				n = e.nativeEvent;
				var r = new n.constructor(n.type, n);
				yn = r, n.target.dispatchEvent(r), yn = null;
			} else return t = It(n), t !== null && mh(t), e.blockedOn = n, !1;
			t.shift();
		}
		return !0;
	}
	function Lh(e, t, n) {
		Ih(e) && n.delete(t);
	}
	function Rh() {
		wh = !1, Th !== null && Ih(Th) && (Th = null), Eh !== null && Ih(Eh) && (Eh = null), Dh !== null && Ih(Dh) && (Dh = null), Oh.forEach(Lh), kh.forEach(Lh);
	}
	function zh(e, n) {
		e.blockedOn === n && (e.blockedOn = null, wh || (wh = !0, t.unstable_scheduleCallback(t.unstable_NormalPriority, Rh)));
	}
	var Bh = null;
	function Vh(e) {
		Bh !== e && (Bh = e, t.unstable_scheduleCallback(t.unstable_NormalPriority, function() {
			Bh === e && (Bh = null);
			for (var t = 0; t < e.length; t += 3) {
				var n = e[t], r = e[t + 1], i = e[t + 2];
				if (typeof r != "function") {
					if (Sh(r || n) === null) continue;
					break;
				}
				var a = It(n);
				a !== null && (e.splice(t, 3), t -= 3, ec(a, {
					pending: !0,
					data: i,
					method: n.method,
					action: r
				}, r, i));
			}
		}));
	}
	function Hh(e) {
		function t(t) {
			return zh(t, e);
		}
		Th !== null && zh(Th, e), Eh !== null && zh(Eh, e), Dh !== null && zh(Dh, e), Oh.forEach(t), kh.forEach(t);
		for (var n = 0; n < Ah.length; n++) {
			var r = Ah[n];
			r.blockedOn === e && (r.blockedOn = null);
		}
		for (; 0 < Ah.length && (n = Ah[0], n.blockedOn === null);) Fh(n), n.blockedOn === null && Ah.shift();
		if (n = (e.ownerDocument || e).$$reactFormReplay, n != null) for (r = 0; r < n.length; r += 3) {
			var i = n[r], a = n[r + 1], o = i[Et] || null;
			if (typeof a == "function") o || Vh(n);
			else if (o) {
				var s = null;
				if (a && a.hasAttribute("formAction")) {
					if (i = a, o = a[Et] || null) s = o.formAction;
					else if (Sh(i) !== null) continue;
				} else s = o.action;
				typeof s == "function" ? n[r + 1] = s : (n.splice(r, 3), r -= 3), Vh(n);
			}
		}
	}
	function Uh() {
		function e(e) {
			e.canIntercept && e.info === "react-transition" && e.intercept({
				handler: function() {
					return new Promise(function(e) {
						return i = e;
					});
				},
				focusReset: "manual",
				scroll: "manual"
			});
		}
		function t() {
			i !== null && (i(), i = null), r || setTimeout(n, 20);
		}
		function n() {
			if (!r && !navigation.transition) {
				var e = navigation.currentEntry;
				e && e.url != null && navigation.navigate(e.url, {
					state: e.getState(),
					info: "react-transition",
					history: "replace"
				});
			}
		}
		if (typeof navigation == "object") {
			var r = !1, i = null;
			return navigation.addEventListener("navigate", e), navigation.addEventListener("navigatesuccess", t), navigation.addEventListener("navigateerror", t), setTimeout(n, 100), function() {
				r = !0, navigation.removeEventListener("navigate", e), navigation.removeEventListener("navigatesuccess", t), navigation.removeEventListener("navigateerror", t), i !== null && (i(), i = null);
			};
		}
	}
	function Wh(e) {
		this._internalRoot = e;
	}
	Gh.prototype.render = Wh.prototype.render = function(e) {
		var t = this._internalRoot;
		if (t === null) throw Error(s(409));
		var n = t.current;
		dh(n, jd(), e, t, null, null);
	}, Gh.prototype.unmount = Wh.prototype.unmount = function() {
		var e = this._internalRoot;
		if (e !== null) {
			this._internalRoot = null;
			var t = e.containerInfo;
			dh(e.current, 2, null, e, null, null), zd(), t[Dt] = null;
		}
	};
	function Gh(e) {
		this._internalRoot = e;
	}
	Gh.prototype.unstable_scheduleHydration = function(e) {
		if (e) {
			var t = Ct();
			e = {
				blockedOn: null,
				target: e,
				priority: t
			};
			for (var n = 0; n < Ah.length && t !== 0 && t < Ah[n].priority; n++);
			Ah.splice(n, 0, e), n === 0 && Fh(e);
		}
	};
	var Kh = r.version;
	if (Kh !== "19.3.1") throw Error(s(527, Kh, "19.3.1"));
	A.findDOMNode = function(e) {
		var t = e._reactInternals;
		if (t === void 0) throw typeof e.render == "function" ? Error(s(188)) : (e = Object.keys(e).join(","), Error(s(268, e)));
		return e = p(t), e = e === null ? null : m(e), e = e === null ? null : e.stateNode, e;
	};
	var qh = {
		bundleType: 0,
		version: "19.3.1",
		rendererPackageName: "react-dom",
		currentDispatcherRef: k,
		reconcilerVersion: "19.3.1"
	};
	if (typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ < "u") {
		var Jh = __REACT_DEVTOOLS_GLOBAL_HOOK__;
		if (!Jh.isDisabled && Jh.supportsFiber) try {
			et = Jh.inject(qh), tt = Jh;
		} catch {}
	}
	e.createRoot = function(e, t) {
		if (!c(e)) throw Error(s(299));
		var n = !1, r = "", i = Cc, a = wc, o = Tc;
		return t != null && (!0 === t.unstable_strictMode && (n = !0), t.identifierPrefix !== void 0 && (r = t.identifierPrefix), t.onUncaughtError !== void 0 && (i = t.onUncaughtError), t.onCaughtError !== void 0 && (a = t.onCaughtError), t.onRecoverableError !== void 0 && (o = t.onRecoverableError)), t = lh(e, 1, !1, null, null, n, r, null, i, a, o, Uh), e[Dt] = t.current, Wf(e), new Wh(t);
	};
})), c = /* @__PURE__ */ e(((e, t) => {
	function n() {
		if (typeof __REACT_DEVTOOLS_GLOBAL_HOOK__ < "u" && typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE == "function") try {
			__REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(n);
		} catch (e) {
			console.error(e);
		}
	}
	n(), t.exports = s();
})), l = i(), u = c();
function d(e, t) {
	return e.available && !e.reference_only && e.mode_tags.includes(t) && e.mode_notes?.[t]?.fit === "direct";
}
function f(e, t) {
	let n = [{
		value: "main",
		label: e === "bordered" ? "中间主图" : "主图"
	}, {
		value: "decoration",
		label: "周围装饰"
	}];
	return e === "scene" && n.push({
		value: "support",
		label: "配角"
	}), e === "bordered" && n.push({
		value: "border",
		label: "上下边饰"
	}), t === "accent" && (e === "scene" || e === "scatter") && n.push({
		value: "accent",
		label: "旧点缀"
	}), n;
}
function p(e, t, n) {
	let r = !1;
	return Object.fromEntries(e.map((e) => {
		let i = n?.[e], a = i && f(t, i).some((e) => e.value === i) ? i : t === "scene" && r ? "support" : "main";
		return a !== "decoration" && (r = !0), [e, a];
	}));
}
function m(e) {
	if (e.layout_engine !== "seamless-unit-v3") return {};
	let t = {};
	return e.asset_refs.forEach((n, r) => {
		let i = e.pattern_roles?.[e.pattern_slots?.[r] || ""];
		i && (t[n] = i);
	}), p(e.asset_refs, e.template_mode, t);
}
var h = class extends Error {
	status;
	code;
	constructor(e, t, n) {
		super(e), this.status = t, this.code = n;
	}
};
async function g(e, t = {}) {
	let n = new Headers(t.headers), r = (t.method || "GET").toUpperCase();
	[
		"GET",
		"HEAD",
		"OPTIONS"
	].includes(r) || n.set("X-HSD-Token", v?.source === _() ? v.value : _()), t.body && !(t.body instanceof FormData) && n.set("Content-Type", "application/json");
	let i = ["GET", "HEAD"].includes(r) ? new AbortController() : null, a = () => i?.abort(t.signal?.reason);
	t.signal?.aborted ? a() : t.signal?.addEventListener("abort", a, { once: !0 });
	let o = i ? setTimeout(() => i.abort(), 15e3) : void 0;
	try {
		let a = () => fetch(`/api/ribbon${e}`, {
			...t,
			headers: n,
			signal: i?.signal || t.signal,
			credentials: "same-origin",
			cache: "no-store"
		}), o = await a();
		if (o.status === 403 && ![
			"GET",
			"HEAD",
			"OPTIONS"
		].includes(r) && (await o.clone().json().catch(() => null))?.code === "page_token_expired") {
			let e = await g("/session", { signal: t.signal });
			if (typeof e.token != "string" || !e.token || e.token.length > 256) throw new h("页面凭证无法更新，请重新载入页面。", 403);
			n.set("X-HSD-Token", e.token), v = {
				source: _(),
				value: e.token
			}, o = await a();
		}
		if (!o.ok) {
			let e = `请求失败（${o.status}）`, t;
			try {
				let n = await o.json();
				typeof n?.code == "string" && (t = n.code), e = typeof n.detail == "string" ? n.detail : typeof n.error == "string" ? n.error : JSON.stringify(n.detail || n);
			} catch {}
			throw new h(e, o.status, t);
		}
		return o.status === 204 ? void 0 : await o.json();
	} catch (e) {
		throw i?.signal.aborted && !t.signal?.aborted ? new h("读取超时，请重试。后台任务不会因此重新提交。", 408) : e;
	} finally {
		clearTimeout(o), t.signal?.removeEventListener("abort", a);
	}
}
var _ = () => "", v = null;
function y(e) {
	_ = e, v = null;
}
var b = (e, t) => g(e, {
	method: "POST",
	body: JSON.stringify(t)
}), ee = (e) => !!e && [
	"QUEUED",
	"RUNNING",
	"RECONCILING"
].includes(e.status), x = (e) => e.sequence === 0 ? "首稿" : `版本 ${e.sequence}`;
function te(e, t) {
	try {
		return JSON.parse(localStorage.getItem(e) || "null") ?? t;
	} catch {
		return t;
	}
}
function S(e, t) {
	try {
		localStorage.setItem(e, JSON.stringify(t));
	} catch {}
}
// node_modules/.pnpm/react@19.3.1/node_modules/react/cjs/react-jsx-runtime.production.js
var C = /* @__PURE__ */ e(((e) => {
	var t = Symbol.for("react.transitional.element"), n = Symbol.for("react.fragment");
	function r(e, n, r) {
		var i = null;
		if (r !== void 0 && (i = "" + r), n.key !== void 0 && (i = "" + n.key), "key" in n) for (var a in r = {}, n) a !== "key" && (r[a] = n[a]);
		else r = n;
		return n = r.ref, {
			$$typeof: t,
			type: e,
			key: i,
			ref: n === void 0 ? null : n,
			props: r
		};
	}
	e.Fragment = n, e.jsx = r, e.jsxs = r;
})), w = (/* @__PURE__ */ e(((e, t) => {
	t.exports = C();
})))(), T = {
	grid: "整齐平铺",
	stagger: "错位平铺",
	scatter: "随机散点",
	single: "单排重复",
	ends: "两端主图",
	panels: "分区拼接",
	bordered: "上下边饰",
	scene: "组合循环",
	fullwidth: "整幅定位",
	alternating: "大小交替",
	ends_open: "两端留白",
	split: "左右分区",
	stacked: "上下分区",
	opposed: "正倒交替"
}, ne = /* @__PURE__ */ new Set([
	"grid",
	"stagger",
	"scatter",
	"single",
	"ends",
	"panels"
]), re = {
	design_background: "首稿底纹",
	generate_background: "生成底图",
	plan: "理解修改要求",
	edit_asset: "修改图案",
	edit_background: "修改底纹",
	edit_composite: "修改整幅"
}, ie = {
	STARTED: "等待结果",
	SUCCEEDED: "已返回",
	FAILED: "失败",
	UNKNOWN: "结果未确认"
}, E = {
	prepare: "准备",
	provider: "服务响应",
	transport: "网络传输",
	validation: "结果校验",
	complete: "结束",
	recovery: "任务恢复",
	unknown: "历史未记录"
};
function ae({ calls: e }) {
	return e?.length ? /* @__PURE__ */ (0, w.jsxs)("details", { children: [/* @__PURE__ */ (0, w.jsxs)("summary", { children: [
		"调用详情（",
		e.length,
		"）"
	] }), /* @__PURE__ */ (0, w.jsx)("ul", { children: e.map((e) => /* @__PURE__ */ (0, w.jsxs)("li", { children: [
		/* @__PURE__ */ (0, w.jsxs)("strong", { children: [
			re[e.operation] || "模型调用",
			" · ",
			ie[e.status] || e.status
		] }),
		e.error && /* @__PURE__ */ (0, w.jsx)("small", { children: e.error }),
		e.diagnostic && /* @__PURE__ */ (0, w.jsxs)("small", { children: [
			E[e.diagnostic.stage] || "未知阶段",
			e.diagnostic.http_status && ` · HTTP ${e.diagnostic.http_status}`,
			e.diagnostic.upstream_code && ` · ${e.diagnostic.upstream_code}`
		] }),
		e.request_id && /* @__PURE__ */ (0, w.jsxs)("small", { children: ["请求编号 ", e.request_id] })
	] }, e.id)) })] }) : null;
}
function oe({ onClose: e, onChanged: t }) {
	let [n, r] = (0, l.useState)("tasks"), [i, a] = (0, l.useState)(null), [o, s] = (0, l.useState)(""), [c, u] = (0, l.useState)(""), [d, f] = (0, l.useState)(!1), [p, m] = (0, l.useState)(""), [h, _] = (0, l.useState)(""), [v, y] = (0, l.useState)("grid"), [ee, x] = (0, l.useState)(!0), [te, S] = (0, l.useState)("{}"), [C, re] = (0, l.useState)("演示输出"), [ie, E] = (0, l.useState)(1800), [oe, se] = (0, l.useState)(300), [D, ce] = (0, l.useState)(150), [le, de] = (0, l.useState)(!0), fe = /* @__PURE__ */ new Map();
	for (let e of i?.provider_calls ?? []) {
		let t = fe.get(e.job_id);
		t ? t.push(e) : fe.set(e.job_id, [e]);
	}
	async function pe() {
		try {
			a(await g("/admin/overview")), s("");
		} catch (e) {
			s(e instanceof Error ? e.message : "加载失败");
		}
	}
	(0, l.useEffect)(() => {
		pe();
	}, []);
	function me(e) {
		m(e.id), _(e.name), y(e.mode), x(e.enabled), S(JSON.stringify(e.rules, null, 2)), u("保存将建立新的配置版本，历史作品不受影响。");
	}
	async function he(e) {
		e.preventDefault(), f(!0), s("");
		try {
			let e = JSON.parse(te);
			if (!e || Array.isArray(e) || typeof e != "object") throw Error("模板规则必须为 JSON 对象。");
			await b("/admin/templates", {
				...p ? { id: p } : {},
				name: h,
				mode: v,
				enabled: ee,
				rules: e
			}), await Promise.all([pe(), t()]), u("模板新版本已保存，样式图已同步。"), m(""), _(""), S("{}");
		} catch (e) {
			s(e instanceof Error ? e.message : "保存失败");
		} finally {
			f(!1);
		}
	}
	async function ge(e) {
		e.preventDefault(), f(!0), s("");
		try {
			if (ie * oe > 4e7) throw Error("总像素不可超过 4000 万。");
			await b("/admin/output-profiles", {
				name: C,
				width: ie,
				height: oe,
				dpi: D,
				format: "PNG",
				is_demo: le
			}), await Promise.all([pe(), t()]), u("新输出配置已启用。已保存的历史版本及其下载文件保持不变。");
		} catch (e) {
			s(e instanceof Error ? e.message : "保存失败");
		} finally {
			f(!1);
		}
	}
	return /* @__PURE__ */ (0, w.jsxs)(ue, {
		title: "内部管理",
		onClose: e,
		wide: !0,
		children: [
			/* @__PURE__ */ (0, w.jsx)("div", {
				className: "admin-tabs",
				children: [
					["tasks", "任务查询"],
					["templates", "排版模式"],
					["output", "输出配置"]
				].map(([e, t]) => /* @__PURE__ */ (0, w.jsx)("button", {
					className: n === e ? "active" : "",
					onClick: () => {
						r(e), s(""), u("");
					},
					children: t
				}, e))
			}),
			o && /* @__PURE__ */ (0, w.jsx)("div", {
				className: "notice error",
				role: "alert",
				children: o
			}),
			c && /* @__PURE__ */ (0, w.jsx)("div", {
				className: "notice success",
				role: "status",
				children: c
			}),
			n === "tasks" && /* @__PURE__ */ (0, w.jsxs)(w.Fragment, { children: [
				/* @__PURE__ */ (0, w.jsxs)("div", {
					className: "admin-intro",
					children: [/* @__PURE__ */ (0, w.jsx)("p", { children: "查询后台任务、执行阶段与失败原因。" }), /* @__PURE__ */ (0, w.jsx)("button", {
						className: "secondary small",
						onClick: () => void pe(),
						children: "刷新任务"
					})]
				}),
				/* @__PURE__ */ (0, w.jsxs)("div", {
					className: "table-scroll",
					children: [/* @__PURE__ */ (0, w.jsxs)("table", { children: [/* @__PURE__ */ (0, w.jsx)("thead", { children: /* @__PURE__ */ (0, w.jsxs)("tr", { children: [
						/* @__PURE__ */ (0, w.jsx)("th", { children: "任务" }),
						/* @__PURE__ */ (0, w.jsx)("th", { children: "状态 / 阶段" }),
						/* @__PURE__ */ (0, w.jsx)("th", { children: "提供商" }),
						/* @__PURE__ */ (0, w.jsx)("th", { children: "尝试" }),
						/* @__PURE__ */ (0, w.jsx)("th", { children: "结果 / 错误" })
					] }) }), /* @__PURE__ */ (0, w.jsx)("tbody", { children: i?.jobs.map((e) => /* @__PURE__ */ (0, w.jsxs)("tr", { children: [
						/* @__PURE__ */ (0, w.jsxs)("td", { children: [/* @__PURE__ */ (0, w.jsx)("strong", { children: e.kind }), /* @__PURE__ */ (0, w.jsxs)("small", {
							title: e.id,
							children: [e.id.slice(0, 12), "…"]
						})] }),
						/* @__PURE__ */ (0, w.jsxs)("td", { children: [/* @__PURE__ */ (0, w.jsx)("span", {
							className: `job-status ${e.status.toLowerCase()}`,
							children: e.status
						}), /* @__PURE__ */ (0, w.jsx)("small", { children: e.phase })] }),
						/* @__PURE__ */ (0, w.jsx)("td", { children: e.provider }),
						/* @__PURE__ */ (0, w.jsx)("td", { children: e.attempt }),
						/* @__PURE__ */ (0, w.jsxs)("td", { children: [e.error || e.result_version_id?.slice(0, 12) || e.result_asset_id?.slice(0, 12) || "—", /* @__PURE__ */ (0, w.jsx)(ae, { calls: fe.get(e.id) })] })
					] }, e.id)) })] }), !i?.jobs.length && /* @__PURE__ */ (0, w.jsx)("div", {
						className: "empty-library",
						children: "暂无后台任务"
					})]
				}),
				/* @__PURE__ */ (0, w.jsx)("p", {
					className: "microcopy",
					children: "素材维护：在工作台素材库中上传或移除；勾选“共享素材”后可供所有账号使用。"
				})
			] }),
			n === "templates" && /* @__PURE__ */ (0, w.jsxs)("div", {
				className: "admin-columns",
				children: [/* @__PURE__ */ (0, w.jsxs)("div", {
					className: "admin-existing",
					children: [/* @__PURE__ */ (0, w.jsx)("h3", { children: "已有模式" }), i?.templates.map((e) => /* @__PURE__ */ (0, w.jsxs)("button", {
						className: `admin-template ${p === e.id ? "selected" : ""}`,
						onClick: () => me(e),
						children: [
							/* @__PURE__ */ (0, w.jsx)("img", {
								src: e.thumbnail_url,
								alt: e.name
							}),
							/* @__PURE__ */ (0, w.jsxs)("div", { children: [/* @__PURE__ */ (0, w.jsx)("strong", { children: e.name }), /* @__PURE__ */ (0, w.jsxs)("small", { children: [
								"版本 ",
								e.version,
								" · ",
								e.enabled ? "已启用" : "已停用"
							] })] }),
							/* @__PURE__ */ (0, w.jsx)(O, {
								name: "arrow",
								size: 15
							})
						]
					}, `${e.id}-${e.version}`))]
				}), /* @__PURE__ */ (0, w.jsxs)("form", {
					onSubmit: he,
					className: "admin-form",
					children: [
						/* @__PURE__ */ (0, w.jsx)("h3", { children: p ? "创建模式新版本" : "新增排版模式" }),
						/* @__PURE__ */ (0, w.jsxs)("label", { children: ["模式名称", /* @__PURE__ */ (0, w.jsx)("input", {
							value: h,
							onChange: (e) => _(e.target.value),
							maxLength: 60,
							required: !0
						})] }),
						/* @__PURE__ */ (0, w.jsxs)("label", { children: ["排版规则类型", /* @__PURE__ */ (0, w.jsx)("select", {
							value: v,
							onChange: (e) => y(e.target.value),
							children: Object.entries(T).map(([e, t]) => /* @__PURE__ */ (0, w.jsx)("option", {
								value: e,
								children: t
							}, e))
						})] }),
						/* @__PURE__ */ (0, w.jsxs)("label", { children: ["规则配置（JSON）", /* @__PURE__ */ (0, w.jsx)("textarea", {
							className: "code-input",
							value: te,
							onChange: (e) => S(e.target.value),
							rows: 5
						})] }),
						/* @__PURE__ */ (0, w.jsxs)("small", {
							className: "template-rules-help",
							children: [ne.has(v) ? "支持 rows（1–4）、step_ratio（0.2–2）、motif_ratio（0.05–0.8）。" : v === "fullwidth" || v === "ends_open" ? "仅支持 motif_ratio（0.05–0.8）调整图案大小；行数固定，不使用 rows 或 step_ratio。" : "支持 step_ratio（0.2–2）、motif_ratio（0.05–0.8）；行数由排法固定，不使用 rows。", "服务端会检查，不适用的字段请移除。"]
						}),
						/* @__PURE__ */ (0, w.jsxs)("label", {
							className: "checkbox-line",
							children: [/* @__PURE__ */ (0, w.jsx)("input", {
								type: "checkbox",
								checked: ee,
								onChange: (e) => x(e.target.checked)
							}), "启用此模式"]
						}),
						/* @__PURE__ */ (0, w.jsx)("button", {
							className: "primary",
							disabled: d,
							children: d ? "保存中…" : "保存新版本"
						}),
						p && /* @__PURE__ */ (0, w.jsx)("button", {
							type: "button",
							className: "text-button",
							onClick: () => {
								m(""), _(""), S("{}"), x(!0);
							},
							children: "改为新增模式"
						})
					]
				})]
			}),
			n === "output" && /* @__PURE__ */ (0, w.jsxs)("div", {
				className: "admin-columns",
				children: [/* @__PURE__ */ (0, w.jsxs)("div", {
					className: "admin-existing",
					children: [
						/* @__PURE__ */ (0, w.jsx)("h3", { children: "配置版本" }),
						/* @__PURE__ */ (0, w.jsx)("p", {
							className: "microcopy",
							children: "固定输出规格只在内部维护。每个作品版本会保存使用的配置快照。"
						}),
						i?.output_profiles.map((e) => /* @__PURE__ */ (0, w.jsxs)("div", {
							className: "profile-item",
							children: [
								/* @__PURE__ */ (0, w.jsxs)("strong", { children: [e.name, /* @__PURE__ */ (0, w.jsxs)("span", {
									className: "tiny-pill",
									children: ["V", e.version]
								})] }),
								/* @__PURE__ */ (0, w.jsxs)("small", { children: [
									e.width,
									" × ",
									e.height,
									" px · ",
									e.dpi,
									" DPI · PNG"
								] }),
								/* @__PURE__ */ (0, w.jsx)("span", { children: e.is_demo ? "演示配置，未完成业务验收" : "正式配置标记（仍需接收软件验收）" })
							]
						}, `${e.id}-${e.version}`))
					]
				}), /* @__PURE__ */ (0, w.jsxs)("form", {
					className: "admin-form",
					onSubmit: ge,
					children: [
						/* @__PURE__ */ (0, w.jsx)("h3", { children: "启用新的输出配置" }),
						/* @__PURE__ */ (0, w.jsxs)("label", { children: ["配置名称", /* @__PURE__ */ (0, w.jsx)("input", {
							value: C,
							onChange: (e) => re(e.target.value),
							required: !0,
							maxLength: 60
						})] }),
						/* @__PURE__ */ (0, w.jsxs)("div", {
							className: "form-two",
							children: [/* @__PURE__ */ (0, w.jsxs)("label", { children: ["宽度（px）", /* @__PURE__ */ (0, w.jsx)("input", {
								type: "number",
								min: 64,
								max: 16e3,
								value: ie,
								onChange: (e) => E(Number(e.target.value)),
								required: !0
							})] }), /* @__PURE__ */ (0, w.jsxs)("label", { children: ["高度（px）", /* @__PURE__ */ (0, w.jsx)("input", {
								type: "number",
								min: 64,
								max: 5e3,
								value: oe,
								onChange: (e) => se(Number(e.target.value)),
								required: !0
							})] })]
						}),
						/* @__PURE__ */ (0, w.jsxs)("label", { children: ["DPI", /* @__PURE__ */ (0, w.jsx)("input", {
							type: "number",
							min: 72,
							max: 1200,
							value: D,
							onChange: (e) => ce(Number(e.target.value)),
							required: !0
						})] }),
						/* @__PURE__ */ (0, w.jsxs)("label", {
							className: "checkbox-line",
							children: [/* @__PURE__ */ (0, w.jsx)("input", {
								type: "checkbox",
								checked: le,
								onChange: (e) => de(e.target.checked)
							}), "演示配置"]
						}),
						/* @__PURE__ */ (0, w.jsx)("p", {
							className: "microcopy",
							children: "当前支持 PNG。正式数值以公司现用文件为准；取消演示标记不代表业务输出已经验收。"
						}),
						/* @__PURE__ */ (0, w.jsx)("button", {
							className: "primary",
							disabled: d,
							children: d ? "保存中…" : "保存并启用新版本"
						})
					]
				})]
			})
		]
	});
}
// src/LayoutExamples.tsx
function se({ url: e, title: t }) {
	let [n, r] = (0, l.useState)(!1), [i, a] = (0, l.useState)(0), o = /^\/static\/ribbon\/layout-v3\/[a-z]+(?:_[a-z]+)*(?:-\d+)?\.webp(?:\?v=[a-z0-9]+)?$/.test(e);
	return (0, l.useEffect)(() => {
		r(!1), a(0);
	}, [e]), !o || n ? /* @__PURE__ */ (0, w.jsxs)("div", {
		className: "layout-example-unavailable",
		children: [/* @__PURE__ */ (0, w.jsx)("p", { children: "程序示例暂未加载。" }), o && /* @__PURE__ */ (0, w.jsx)("button", {
			className: "secondary small",
			onClick: () => {
				r(!1), a((e) => e + 1);
			},
			children: "重试示例"
		})]
	}) : /* @__PURE__ */ (0, w.jsx)("img", {
		src: e,
		alt: t,
		loading: "lazy",
		decoding: "async",
		onError: () => r(!0)
	}, `${e}-${i}`);
}
function D(e) {
	if (!e?.startsWith("/api/ribbon/layout-examples/")) return null;
	try {
		let t = new URL(e, location.href);
		return t.origin === location.origin && t.pathname.endsWith("/image") ? t.href : null;
	} catch {
		return null;
	}
}
function ce({ example: e }) {
	let [t, n] = (0, l.useState)(!1), [r, i] = (0, l.useState)(!1), [a, o] = (0, l.useState)(0), s = (0, l.useRef)(null), c = e.available ? D(e.image_url) : null;
	return (0, l.useEffect)(() => {
		i(!1), n(!1), o(0);
	}, [
		e.id,
		e.image_url,
		e.available
	]), !c || r ? /* @__PURE__ */ (0, w.jsxs)("div", {
		className: "layout-example-unavailable",
		role: "status",
		children: [/* @__PURE__ */ (0, w.jsx)("p", { children: r ? "案例图片没有加载成功，排版说明仍可查看。" : "这张案例图暂未加载，排版说明仍可查看。" }), c && /* @__PURE__ */ (0, w.jsx)("button", {
			type: "button",
			className: "secondary",
			onClick: () => {
				i(!1), o((e) => e + 1);
			},
			children: "重试图片"
		})]
	}) : /* @__PURE__ */ (0, w.jsxs)(w.Fragment, { children: [/* @__PURE__ */ (0, w.jsxs)("div", {
		className: "layout-example-image-tools",
		children: [/* @__PURE__ */ (0, w.jsx)("button", {
			type: "button",
			className: "text-button",
			"aria-pressed": t,
			"aria-label": `${t ? "查看整条" : "放大查看"} ${e.code}`,
			onClick: () => {
				n((e) => !e), s.current && (s.current.scrollLeft = 0);
			},
			children: t ? "查看整条" : "放大查看"
		}), t && /* @__PURE__ */ (0, w.jsx)("span", { children: "可左右滚动查看" })]
	}), /* @__PURE__ */ (0, w.jsx)("div", {
		ref: s,
		className: `layout-example-viewport${t ? " is-zoomed" : ""}`,
		role: "region",
		"aria-label": `${e.code} 案例图${t ? "，可左右滚动" : ""}`,
		tabIndex: t ? 0 : -1,
		style: { "--example-width": `${e.width}px` },
		children: /* @__PURE__ */ (0, w.jsx)("img", {
			src: c,
			width: e.width,
			height: e.height,
			alt: `${e.title}，图库图号 ${e.code}`,
			loading: "lazy",
			decoding: "async",
			referrerPolicy: "same-origin",
			onError: () => i(!0)
		}, `${e.id}-${e.image_url}-${a}`)
	})] });
}
function le({ mode: e, cache: t, onUnauthorized: n, onViewAll: r, referenceMode: i, onChooseReference: a, legacyLayout: o = !1 }) {
	let [s, c] = (0, l.useState)(() => t.current), [u, f] = (0, l.useState)(!t.current), [p, m] = (0, l.useState)(""), [_, v] = (0, l.useState)(0), y = (0, l.useRef)(n);
	y.current = n;
	let b = (0, l.useRef)(null), [ee, x] = (0, l.useState)(0), [te, S] = (0, l.useState)(""), [C, T] = (0, l.useState)("company");
	(0, l.useEffect)(() => {
		if (t.current) {
			c(t.current), f(!1);
			return;
		}
		let e = new AbortController(), n = !1;
		return f(!0), m(""), g("/layout-examples", { signal: e.signal }).then((e) => {
			n || (t.current = e, c(e));
		}).catch((e) => {
			n || (m(e instanceof Error ? e.message : "请稍后重新加载案例。"), e instanceof h && e.status === 401 && y.current());
		}).finally(() => {
			n || f(!1);
		}), () => {
			n = !0, e.abort();
		};
	}, [t, _]), (0, l.useEffect)(() => {
		b.current?.closest(".modal")?.scrollTo({ top: 0 }), x(0), S(""), T("company");
	}, [e]);
	function ne() {
		t.current = null, c(null), v((e) => e + 1);
	}
	if (u) return /* @__PURE__ */ (0, w.jsxs)("div", {
		className: "layout-examples-loading",
		role: "status",
		children: [/* @__PURE__ */ (0, w.jsx)("span", { className: "spinner" }), "正在加载排版案例…"]
	});
	if (p || !s) return /* @__PURE__ */ (0, w.jsxs)("div", {
		className: "layout-examples-error",
		role: "alert",
		children: [/* @__PURE__ */ (0, w.jsxs)("p", { children: ["案例暂时无法打开：", p || "请稍后再试。"] }), /* @__PURE__ */ (0, w.jsx)("button", {
			type: "button",
			className: "secondary",
			onClick: ne,
			children: "重新加载案例"
		})]
	});
	let re = e || te, ie = s.modes.find((e) => e.mode === re), E = re ? (ie?.example_ids || []).flatMap((e) => s.examples.filter((t) => t.id === e)) : s.examples, ae = Math.min(ee, Math.max(0, E.length - 1)), oe = re ? E.slice(ae, ae + 1) : E;
	return /* @__PURE__ */ (0, w.jsxs)("div", {
		className: "layout-examples",
		ref: b,
		children: [
			/* @__PURE__ */ (0, w.jsxs)("div", {
				className: "layout-examples-intro",
				children: [
					ie && /* @__PURE__ */ (0, w.jsx)("p", {
						className: "layout-mode-summary",
						children: ie.summary
					}),
					ie?.note && /* @__PURE__ */ (0, w.jsx)("p", {
						className: "layout-mode-note",
						children: ie.note
					}),
					!e && /* @__PURE__ */ (0, w.jsx)("p", {
						className: "layout-mode-summary",
						children: a ? "案例可查看，也可明确选择为 AI 首稿参考。只有与当前排法匹配的可用案例可以选中。" : "先看排列方式，再选择适合的排版。案例只说明结构，生成时使用你自己选择的素材。"
					}),
					a && /* @__PURE__ */ (0, w.jsx)("p", {
						className: "layout-reference-help",
						children: "查看不会发送案例。只有明确选为参考后，生成 AI 首稿时才把所选案例发送给 Seedream。"
					}),
					e && !ie && /* @__PURE__ */ (0, w.jsx)("p", { children: "当前排版暂无对应的公司案例，可先查看其他排法。" }),
					/* @__PURE__ */ (0, w.jsxs)("div", {
						className: "layout-examples-tools",
						children: [
							e && /* @__PURE__ */ (0, w.jsx)("button", {
								type: "button",
								className: "secondary",
								onClick: r,
								children: "查看全部案例"
							}),
							!e && /* @__PURE__ */ (0, w.jsxs)("label", {
								className: "case-mode-filter",
								children: ["排版", /* @__PURE__ */ (0, w.jsxs)("select", {
									"aria-label": "筛选排版案例",
									value: te,
									onChange: (e) => {
										S(e.target.value), x(0), T("company");
									},
									children: [/* @__PURE__ */ (0, w.jsx)("option", {
										value: "",
										children: "全部"
									}), s.modes.map((e) => /* @__PURE__ */ (0, w.jsx)("option", {
										value: e.mode,
										children: e.name
									}, e.mode))]
								})]
							}),
							/* @__PURE__ */ (0, w.jsx)("button", {
								type: "button",
								className: "text-button",
								onClick: ne,
								children: "重新加载"
							})
						]
					})
				]
			}),
			ie?.demo_variants?.length ? /* @__PURE__ */ (0, w.jsxs)("div", {
				className: "layout-example-kind",
				role: "group",
				"aria-label": "参考类型",
				children: [/* @__PURE__ */ (0, w.jsxs)("button", {
					className: C === "company" ? "selected" : "",
					"aria-pressed": C === "company",
					onClick: () => T("company"),
					children: [
						"公司案例（",
						E.length,
						"）"
					]
				}), /* @__PURE__ */ (0, w.jsxs)("button", {
					className: C === "demo" ? "selected" : "",
					"aria-pressed": C === "demo",
					onClick: () => T("demo"),
					children: [
						"程序示例（",
						ie.demo_variants.length,
						"）"
					]
				})]
			}) : null,
			C === "demo" && ie ? /* @__PURE__ */ (0, w.jsxs)("div", {
				className: "layout-demos",
				children: [
					/* @__PURE__ */ (0, w.jsx)("p", {
						className: "layout-demo-note",
						children: "以下用自制素材实际排版，说明素材数量与角色怎样影响结果，不是公司原稿或 AI 生图。"
					}),
					o && /* @__PURE__ */ (0, w.jsx)("p", {
						className: "layout-demo-note",
						children: "程序示例展示新版排法。当前旧作品继续使用原排版规则，新建作品才会使用新版。"
					}),
					(ie.demo_variants || []).map((e) => /* @__PURE__ */ (0, w.jsxs)("figure", { children: [/* @__PURE__ */ (0, w.jsxs)("figcaption", { children: [/* @__PURE__ */ (0, w.jsx)("strong", { children: e.title }), /* @__PURE__ */ (0, w.jsx)("span", { children: e.description })] }), /* @__PURE__ */ (0, w.jsx)(se, {
						url: e.image_url,
						title: e.title
					})] }, e.id))
				]
			}) : /* @__PURE__ */ (0, w.jsxs)(w.Fragment, { children: [
				re && E.length > 1 && /* @__PURE__ */ (0, w.jsxs)("nav", {
					className: "layout-case-navigation",
					"aria-label": "本排法案例",
					children: [
						/* @__PURE__ */ (0, w.jsx)("button", {
							className: "secondary small",
							disabled: ae === 0,
							onClick: () => x(ae - 1),
							children: "上一例"
						}),
						/* @__PURE__ */ (0, w.jsxs)("label", { children: [/* @__PURE__ */ (0, w.jsxs)("span", { children: [
							"案例 ",
							ae + 1,
							" / ",
							E.length
						] }), /* @__PURE__ */ (0, w.jsx)("select", {
							"aria-label": "选择案例",
							value: E[ae].id,
							onChange: (e) => x(E.findIndex((t) => t.id === e.target.value)),
							children: E.map((e, t) => /* @__PURE__ */ (0, w.jsxs)("option", {
								value: e.id,
								children: [
									t + 1,
									". ",
									e.title
								]
							}, e.id))
						})] }),
						/* @__PURE__ */ (0, w.jsx)("button", {
							className: "secondary small",
							disabled: ae === E.length - 1,
							onClick: () => x(ae + 1),
							children: "下一例"
						})
					]
				}),
				/* @__PURE__ */ (0, w.jsx)("div", {
					className: "layout-examples-list",
					children: oe.map((e) => {
						let t = re ? e.mode_notes?.[re] : void 0;
						return /* @__PURE__ */ (0, w.jsxs)("article", {
							className: "layout-example",
							children: [
								/* @__PURE__ */ (0, w.jsxs)("div", {
									className: "layout-example-heading",
									children: [/* @__PURE__ */ (0, w.jsx)("h3", { children: e.title }), /* @__PURE__ */ (0, w.jsxs)("div", { children: [
										e.reference_only && /* @__PURE__ */ (0, w.jsx)("span", {
											className: "layout-reference-tag",
											children: "延展参考"
										}),
										t?.fit === "partial" && /* @__PURE__ */ (0, w.jsx)("span", {
											className: "layout-reference-tag",
											children: "组合参考"
										}),
										/* @__PURE__ */ (0, w.jsx)("span", {
											className: "layout-example-code",
											children: e.code
										})
									] })]
								}),
								/* @__PURE__ */ (0, w.jsx)("p", {
									className: "layout-example-description",
									children: e.description
								}),
								!re && s.modes.filter((t) => t.example_ids.includes(e.id)).map((e) => /* @__PURE__ */ (0, w.jsxs)("p", {
									className: "layout-mode-note",
									children: [/* @__PURE__ */ (0, w.jsxs)("strong", { children: [e.name, "："] }), e.note]
								}, e.mode)),
								/* @__PURE__ */ (0, w.jsx)(ce, { example: e }),
								/* @__PURE__ */ (0, w.jsxs)("p", {
									className: "layout-example-look",
									children: [/* @__PURE__ */ (0, w.jsx)("strong", { children: "看点：" }), t?.look_for || (Array.isArray(e.look_for) ? e.look_for.join("；") : e.look_for)]
								}),
								t?.difference && /* @__PURE__ */ (0, w.jsxs)("p", {
									className: "layout-example-difference",
									children: [/* @__PURE__ */ (0, w.jsx)("strong", { children: "与当前排法的区别：" }), t.difference]
								}),
								e.reference_only && /* @__PURE__ */ (0, w.jsx)("p", {
									className: "layout-example-reference",
									children: "当前没有单独的对应排版选项，不会因查看案例自动生成这种效果。"
								}),
								a && i && d(e, i) && D(e.image_url) && /* @__PURE__ */ (0, w.jsx)("button", {
									type: "button",
									className: "secondary choose-ai-reference",
									onClick: () => a(e),
									children: "用于AI首稿参考"
								})
							]
						}, e.id);
					})
				}),
				!E.length && /* @__PURE__ */ (0, w.jsx)("p", {
					className: "layout-example-unavailable",
					children: "暂时没有对应案例，请查看全部案例或稍后重新加载。"
				})
			] }),
			/* @__PURE__ */ (0, w.jsxs)("p", {
				className: "layout-examples-source",
				children: [
					s.source_name,
					" · ",
					s.note
				]
			})
		]
	});
}
// src/App.tsx
function O({ name: e, size: t = 18 }) {
	return /* @__PURE__ */ (0, w.jsx)("svg", {
		width: t,
		height: t,
		viewBox: "0 0 24 24",
		fill: "none",
		stroke: "currentColor",
		strokeWidth: "1.65",
		strokeLinecap: "round",
		strokeLinejoin: "round",
		"aria-hidden": "true",
		children: {
			spark: /* @__PURE__ */ (0, w.jsxs)(w.Fragment, { children: [/* @__PURE__ */ (0, w.jsx)("path", { d: "m12 3 2.3 6.7L21 12l-6.7 2.3L12 21l-2.3-6.7L3 12l6.7-2.3Z" }), /* @__PURE__ */ (0, w.jsx)("path", { d: "m20 2 .7 2.3L23 5l-2.3.7L20 8l-.7-2.3L17 5l2.3-.7Z" })] }),
			upload: /* @__PURE__ */ (0, w.jsx)(w.Fragment, { children: /* @__PURE__ */ (0, w.jsx)("path", { d: "M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6" }) }),
			grid: /* @__PURE__ */ (0, w.jsxs)(w.Fragment, { children: [
				/* @__PURE__ */ (0, w.jsx)("rect", {
					x: "3",
					y: "3",
					width: "7",
					height: "7",
					rx: "1"
				}),
				/* @__PURE__ */ (0, w.jsx)("rect", {
					x: "14",
					y: "3",
					width: "7",
					height: "7",
					rx: "1"
				}),
				/* @__PURE__ */ (0, w.jsx)("rect", {
					x: "3",
					y: "14",
					width: "7",
					height: "7",
					rx: "1"
				}),
				/* @__PURE__ */ (0, w.jsx)("rect", {
					x: "14",
					y: "14",
					width: "7",
					height: "7",
					rx: "1"
				})
			] }),
			back: /* @__PURE__ */ (0, w.jsx)(w.Fragment, { children: /* @__PURE__ */ (0, w.jsx)("path", { d: "m8 4-5 5 5 5M3 9h10a7 7 0 0 1 0 14" }) }),
			download: /* @__PURE__ */ (0, w.jsx)(w.Fragment, { children: /* @__PURE__ */ (0, w.jsx)("path", { d: "M12 3v13m-5-5 5 5 5-5M4 17v4h16v-4" }) }),
			plus: /* @__PURE__ */ (0, w.jsx)("path", { d: "M12 4v16M4 12h16" }),
			close: /* @__PURE__ */ (0, w.jsx)("path", { d: "m6 6 12 12M6 18 18 6" }),
			check: /* @__PURE__ */ (0, w.jsx)("path", { d: "m4 12 5 5L20 6" }),
			folder: /* @__PURE__ */ (0, w.jsx)("path", { d: "M3 6h7l2 3h9v11H3ZM3 6V4h7l2 2" }),
			arrow: /* @__PURE__ */ (0, w.jsx)("path", { d: "M4 12h16m-6-6 6 6-6 6" }),
			logout: /* @__PURE__ */ (0, w.jsx)(w.Fragment, { children: /* @__PURE__ */ (0, w.jsx)("path", { d: "M9 4H3v16h6m5-13 5 5-5 5M8 12h11" }) }),
			settings: /* @__PURE__ */ (0, w.jsxs)(w.Fragment, { children: [/* @__PURE__ */ (0, w.jsx)("circle", {
				cx: "12",
				cy: "12",
				r: "4"
			}), /* @__PURE__ */ (0, w.jsx)("path", { d: "m12 2 2 3 4-1 1 4 3 2-2 3 1 4-4 1-2 3-3-2-4 1-1-4-3-2 2-3-1-4 4-1Z" })] })
		}[e]
	});
}
function ue({ title: e, children: t, onClose: n, wide: r = !1, className: i = "" }) {
	let a = (0, l.useRef)(null);
	return (0, l.useEffect)(() => {
		let e = a.current?.getRootNode(), t = e?.activeElement;
		(a.current?.querySelector("button,input,select,textarea"))?.focus();
		let r = (t) => {
			if (t.key === "Escape" && n(), t.key === "Tab") {
				let n = a.current?.querySelectorAll("button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex=\"0\"]");
				if (!n?.length) return;
				let r = n[0], i = n[n.length - 1];
				t.shiftKey && e?.activeElement === r ? (t.preventDefault(), i.focus()) : !t.shiftKey && e?.activeElement === i && (t.preventDefault(), r.focus());
			}
		};
		document.addEventListener("keydown", r);
		let i = document.body.style.overflow;
		return document.body.style.overflow = "hidden", () => {
			document.removeEventListener("keydown", r), document.body.style.overflow = i, t?.focus();
		};
	}, []), /* @__PURE__ */ (0, w.jsx)("div", {
		className: "modal-scrim",
		onMouseDown: (e) => {
			e.target === e.currentTarget && n();
		},
		children: /* @__PURE__ */ (0, w.jsxs)("div", {
			ref: a,
			className: `modal ${r ? "modal-wide" : ""} ${i}`,
			role: "dialog",
			"aria-modal": "true",
			"aria-label": e,
			children: [/* @__PURE__ */ (0, w.jsxs)("div", {
				className: "modal-heading",
				children: [/* @__PURE__ */ (0, w.jsx)("div", { children: /* @__PURE__ */ (0, w.jsx)("h2", { children: e }) }), /* @__PURE__ */ (0, w.jsx)("button", {
					className: "icon-button",
					"aria-label": "关闭弹窗",
					onClick: n,
					children: /* @__PURE__ */ (0, w.jsx)(O, { name: "close" })
				})]
			}), t]
		})
	});
}
function de() {
	return /* @__PURE__ */ (0, w.jsxs)("div", {
		className: "brand",
		children: [/* @__PURE__ */ (0, w.jsx)("span", {
			className: "brand-icon",
			children: /* @__PURE__ */ (0, w.jsxs)("svg", {
				width: "26",
				height: "30",
				viewBox: "0 0 26 30",
				fill: "none",
				children: [/* @__PURE__ */ (0, w.jsx)("path", {
					d: "M5 3h16v12L13 9 5 15V3Z",
					fill: "currentColor"
				}), /* @__PURE__ */ (0, w.jsx)("path", {
					d: "M5 19v8l8-5 8 5V16l-8-5-8 5",
					stroke: "currentColor",
					strokeWidth: "2"
				})]
			})
		}), /* @__PURE__ */ (0, w.jsx)("div", { children: /* @__PURE__ */ (0, w.jsx)("strong", { children: "丝带设计助手" }) })]
	});
}
function fe(e) {
	return e instanceof Error ? e.message : "发生未知错误，请重试。";
}
var pe = {
	asset_ids: [],
	background_id: "",
	template_id: "",
	background_tone: "soft",
	design_density: "balanced",
	design_style: "classic"
}, me = /* @__PURE__ */ new Set([
	"grid",
	"stagger",
	"scatter",
	"single",
	"ends",
	"panels"
]), he = {
	grid: "完整图案按行排列，保持比例；可用画面密度选择疏朗或饱满。",
	stagger: "相邻行错开，整组图案连续重复；文字和装饰作为一个整体保留。",
	scatter: "轻微错落排列，默认保持图案朝向；不会自动拆出小装饰。",
	single: "适合文字或较大的主体，多个图案按选择顺序整组重复。",
	bordered: "第一个图案放中间，其余图案做上下边饰；至少选择 2 个图案。",
	scene: "第一个图案作主图，其余稍小、底部对齐，再整组循环；辅助装饰需自行选入。",
	fullwidth: "使用 1 个主图，保持完整比例；循环作品会将整幅作为一个单元重复。",
	alternating: "图案一大一小依次重复，可选择 1–12 个图案。",
	ends_open: "用 1–2 个主图放在两端，中间留白；循环作品会将两端与留白作为完整面板重复。",
	split: "至少使用 2 个主图，前半组放左侧，后半组放右侧。",
	stacked: "至少使用 2 个主图，前半组放上方，后半组放下方。",
	opposed: "相邻图案正向、倒置交替，旋转 180°，不会镜像翻字。"
}, ge = {
	left: "左区",
	center: "中区",
	right: "右区",
	top: "上区",
	bottom: "下区"
}, _e = {
	panels: [
		"left",
		"center",
		"right"
	],
	split: ["left", "right"],
	stacked: ["top", "bottom"]
}, ve = {
	scene: "主图和配角在同一底线上，周围装饰排入空隙；完整人物和文字不拆开。",
	scatter: "主图错落倾斜，周围装饰填入空隙；不会自动把主图缩成装饰。",
	bordered: "主图排在中间。需要小图沿上下边排列时，将它设为上下边饰，也可另选完整边饰条。"
}, ye = {
	scatter: "完整图案以不同角度和大小错落分布，整个单元循环。",
	bordered: "中央重复主图，上下为连续边线，可选独立边饰。",
	panels: "左、中、右三区各自排放图案，可分别选择底纹。"
};
function be(e, t, n = !1) {
	return t ? e === "fullwidth" && t !== 1 ? "整幅定位只使用 1 个主图。其余图案可设为周围装饰。" : e === "ends_open" && t > 2 ? "两端留白最多使用 2 个主图。其余图案可设为周围装饰。" : e && (!n && e === "bordered" || ["split", "stacked"].includes(e)) && t < 2 ? "这类排版至少需要 2 个主图，周围装饰不计入。" : "" : "";
}
function xe(e, t) {
	return {
		asset_ids: [
			"demo-flower",
			"demo-star",
			"demo-ring"
		].filter((t) => e.some((e) => e.id === t)),
		background_id: e.find((e) => e.id === "demo-bg-sage")?.id || "",
		background_tone: "soft",
		design_density: "balanced",
		template_id: t.find((e) => e.mode === "stagger" && e.enabled)?.id || t.find((e) => e.enabled)?.id || ""
	};
}
function k(e, t) {
	let n = t?.snapshot;
	return {
		...e,
		background_tone: e.background_tone ?? n?.background_tone ?? (t ? "original" : "soft"),
		design_density: e.design_density ?? n?.design_density ?? "balanced",
		design_style: e.design_style ?? n?.design_style ?? "classic"
	};
}
function A({ version: e, sizeLabel: t }) {
	let [n, r] = (0, l.useState)(!1), [i, a] = (0, l.useState)(!1), o = e.snapshot.loop, s = e.snapshot.output_profile_source;
	return /* @__PURE__ */ (0, w.jsxs)("div", {
		className: "loop-preview",
		children: [
			/* @__PURE__ */ (0, w.jsxs)("div", {
				className: "loop-view-heading",
				children: [/* @__PURE__ */ (0, w.jsx)("strong", { children: n ? "连续效果预览" : "循环单元" }), /* @__PURE__ */ (0, w.jsx)("span", { children: n ? "同一单元横向重复 3 次" : t })]
			}),
			/* @__PURE__ */ (0, w.jsx)("div", {
				className: "loop-unit-view",
				hidden: n,
				children: /* @__PURE__ */ (0, w.jsx)("div", {
					className: "loop-image",
					children: /* @__PURE__ */ (0, w.jsx)(Se, {
						src: e.preview_url,
						decoding: "async",
						alt: `${x(e)}的循环单元预览`
					})
				})
			}),
			/* @__PURE__ */ (0, w.jsx)("div", {
				className: "loop-continuity",
				hidden: !n,
				children: /* @__PURE__ */ (0, w.jsx)("div", {
					className: `loop-continuity-track ${i ? "show-seams" : ""}`,
					children: [
						0,
						1,
						2
					].map((t) => /* @__PURE__ */ (0, w.jsx)("div", {
						className: "loop-repeat",
						children: /* @__PURE__ */ (0, w.jsx)(Se, {
							src: e.preview_url,
							decoding: "async",
							alt: t === 0 ? `${x(e)}的三次连续效果预览` : ""
						})
					}, t))
				})
			}),
			/* @__PURE__ */ (0, w.jsxs)("div", {
				className: "loop-preview-tools",
				children: [/* @__PURE__ */ (0, w.jsx)("button", {
					type: "button",
					className: "loop-view-button",
					"aria-pressed": n,
					onClick: () => r((e) => !e),
					children: n ? "返回循环单元" : "查看连续效果"
				}), n && /* @__PURE__ */ (0, w.jsxs)("label", {
					className: "loop-seam-toggle",
					children: [/* @__PURE__ */ (0, w.jsx)("input", {
						type: "checkbox",
						checked: i,
						onChange: (e) => a(e.target.checked)
					}), "显示接缝位置"]
				})]
			}),
			o.status === "needs_review" && /* @__PURE__ */ (0, w.jsxs)("div", {
				className: "loop-check needs-review",
				children: [/* @__PURE__ */ (0, w.jsx)("strong", { children: "接缝提示" }), !!o.issues?.length && /* @__PURE__ */ (0, w.jsx)("ul", {
					"aria-label": "循环检查提示",
					children: o.issues.map((e, t) => /* @__PURE__ */ (0, w.jsx)("li", {
						className: e.severity,
						children: e.message
					}, `${e.code}:${t}`))
				})]
			}),
			o.mode_notice && /* @__PURE__ */ (0, w.jsx)("p", {
				className: "loop-mode-notice",
				children: o.mode_notice
			}),
			!!o.motif_resolution?.note && /* @__PURE__ */ (0, w.jsx)("p", {
				className: "loop-resolution-note",
				children: o.motif_resolution.note
			}),
			/* @__PURE__ */ (0, w.jsxs)("details", {
				className: "loop-technical-details",
				children: [
					/* @__PURE__ */ (0, w.jsx)("summary", { children: "输出详情" }),
					o.status === "checked" && /* @__PURE__ */ (0, w.jsx)("strong", { children: "工程循环检查通过" }),
					/* @__PURE__ */ (0, w.jsx)("p", { children: "下载为一个原尺寸循环单元。工程检查只核对排版和接缝，印刷效果需另行核样。" }),
					/* @__PURE__ */ (0, w.jsxs)("dl", { children: [
						/* @__PURE__ */ (0, w.jsxs)("div", { children: [/* @__PURE__ */ (0, w.jsx)("dt", { children: "下载尺寸" }), /* @__PURE__ */ (0, w.jsx)("dd", { children: t || `${o.width}×${o.height}px` })] }),
						/* @__PURE__ */ (0, w.jsxs)("div", { children: [/* @__PURE__ */ (0, w.jsx)("dt", { children: "循环方式" }), /* @__PURE__ */ (0, w.jsx)("dd", { children: o.kind === "panel" ? "定位区段循环" : "图案序列循环" })] }),
						/* @__PURE__ */ (0, w.jsxs)("div", { children: [/* @__PURE__ */ (0, w.jsx)("dt", { children: "检查引擎" }), /* @__PURE__ */ (0, w.jsx)("dd", { children: o.engine })] }),
						o.rhythm && /* @__PURE__ */ (0, w.jsxs)("div", { children: [/* @__PURE__ */ (0, w.jsx)("dt", { children: "重复节奏" }), /* @__PURE__ */ (0, w.jsxs)("dd", { children: [o.rhythm.repeats_to_length ? `100cm 约 ${o.rhythm.repeats_to_length} 个单元` : `${o.rhythm.unit_width}px 单元`, o.rhythm.size_variety > 1.05 ? ` · 尺寸差 ${o.rhythm.size_variety}×` : " · 尺寸一致"] })] }),
						s && /* @__PURE__ */ (0, w.jsxs)("div", { children: [/* @__PURE__ */ (0, w.jsx)("dt", { children: "来源配置" }), /* @__PURE__ */ (0, w.jsxs)("dd", { children: [s.name, s.width && s.height ? ` · ${s.width}×${s.height}px` : ""] })] })
					] })
				]
			})
		]
	});
}
function Se({ src: e, alt: t, quiet: n, ...r }) {
	let [i, a] = (0, l.useState)(0), [o, s] = (0, l.useState)(!1), [c, u] = (0, l.useState)(!1);
	(0, l.useEffect)(() => {
		a(0), s(!1), u(!1);
	}, [e]);
	let d = i ? e + (e.includes("?") ? "&" : "?") + "retry=" + i : e, f = () => {
		s(!1), u(!1), a((e) => e + 1);
	};
	return /* @__PURE__ */ (0, w.jsxs)(w.Fragment, { children: [!o && /* @__PURE__ */ (0, w.jsx)("img", {
		...r,
		src: d,
		alt: t,
		onLoad: () => u(!0),
		onError: () => s(!0)
	}), o ? n ? /* @__PURE__ */ (0, w.jsx)("span", {
		className: "image-quiet",
		role: "presentation",
		title: `${t || "图片"}暂不可用`,
		children: /* @__PURE__ */ (0, w.jsx)(O, {
			name: "grid",
			size: 14
		})
	}) : /* @__PURE__ */ (0, w.jsxs)("span", {
		className: "image-recovery",
		role: "status",
		children: [/* @__PURE__ */ (0, w.jsxs)("span", { children: [t || "图片", "加载失败"] }), /* @__PURE__ */ (0, w.jsx)("span", {
			role: "button",
			tabIndex: 0,
			className: "secondary small",
			onClick: (e) => {
				e.stopPropagation(), f();
			},
			onKeyDown: (e) => {
				(e.key === "Enter" || e.key === " ") && (e.preventDefault(), e.stopPropagation(), f());
			},
			children: "重新加载图片"
		})]
	}) : !c && r.loading !== "lazy" && /* @__PURE__ */ (0, w.jsx)("span", {
		className: "image-loading",
		children: "图片加载中…"
	})] });
}
var Ce = {
	queued: "等待处理",
	planning: "正在准备设计",
	rendering: "正在生成设计",
	editing: "正在编辑图像",
	saving: "正在保存结果",
	completed: "已保存",
	generating: "正在生成底图",
	validating: "正在检查结果",
	reconciling: "正在恢复任务",
	QUEUED: "等待处理",
	RUNNING: "正在处理",
	RECONCILING: "正在恢复任务",
	SUCCEEDED: "已保存",
	FAILED: "处理未完成"
};
function we({ active: e, view: t }) {
	let [n, r] = (0, l.useState)(null), [i, a] = (0, l.useState)(!0), [o, s] = (0, l.useState)(""), [c, u] = (0, l.useState)(!1), [d, f] = (0, l.useState)(0), p = (0, l.useRef)(0);
	function m() {
		++p.current, r(null), a(!1), u(!0), s("登录已失效，请重新打开网站后继续。");
	}
	return (0, l.useEffect)(() => {
		if (!e) return;
		let t = !1, n = ++p.current, i = new AbortController(), o = () => t || i.signal.aborted || n !== p.current;
		return a(!0), s(""), g("/auth/me", { signal: i.signal }).then((e) => {
			o() || (r(e), u(!1));
		}).catch((e) => {
			o() || (e instanceof h && e.status === 401 && (r(null), u(!0)), s(fe(e)));
		}).finally(() => {
			o() || a(!1);
		}), () => {
			t = !0, i.abort();
		};
	}, [
		e,
		t,
		d
	]), /* @__PURE__ */ (0, w.jsxs)(w.Fragment, { children: [
		i && !n && /* @__PURE__ */ (0, w.jsxs)("div", {
			className: "page-loader",
			children: [/* @__PURE__ */ (0, w.jsx)("span", { className: "spinner" }), /* @__PURE__ */ (0, w.jsx)("span", { children: "正在连接丝带设计…" })]
		}),
		!i && !n && /* @__PURE__ */ (0, w.jsxs)("div", {
			className: "notice error",
			role: "alert",
			children: [
				/* @__PURE__ */ (0, w.jsx)("strong", { children: "丝带设计暂时无法打开" }),
				/* @__PURE__ */ (0, w.jsx)("p", { children: o || "连接暂时中断，请重试。" }),
				/* @__PURE__ */ (0, w.jsx)("button", {
					type: "button",
					onClick: () => c ? location.reload() : f((e) => e + 1),
					children: c ? "重新登录" : "重新连接"
				})
			]
		}),
		n && o && /* @__PURE__ */ (0, w.jsxs)("div", {
			className: "notice error",
			role: "alert",
			children: [
				/* @__PURE__ */ (0, w.jsx)("strong", { children: "连接暂时中断，已保留当前作品。" }),
				/* @__PURE__ */ (0, w.jsx)("p", { children: o }),
				/* @__PURE__ */ (0, w.jsx)("button", {
					type: "button",
					onClick: () => f((e) => e + 1),
					disabled: i,
					children: "重新连接"
				})
			]
		}),
		n && /* @__PURE__ */ (0, w.jsx)(Te, {
			user: n,
			active: e && !i,
			view: t,
			onLogout: m
		}, n.id)
	] });
}
function Te({ user: e, onLogout: t, active: n, view: r }) {
	let i = `ribbon:${e.id}:`, [a, o] = (0, l.useState)(() => te(i + "creationUncertain", !1) === !0), [s] = (0, l.useState)(() => a ? te(i + "creationDraft", null) : null), c = (0, l.useRef)(a), u = (0, l.useRef)(s), [_, v] = (0, l.useState)(0), [y, C] = (0, l.useState)(""), [T, ne] = (0, l.useState)(!1), [re, ie] = (0, l.useState)(""), [E, ae] = (0, l.useState)(!1), se = (0, l.useRef)(null), [D, ce] = (0, l.useState)(null), [we, Te] = (0, l.useState)([]), [Ee, j] = (0, l.useState)([]), [De, Oe] = (0, l.useState)([{
		id: "classic",
		label: "经典等距",
		hint: "保持原有节奏"
	}]), [ke, Ae] = (0, l.useState)(null), [je, Me] = (0, l.useState)(() => {
		let e = te(i + "trialStyles", []).filter((e) => typeof e == "string");
		return e.length >= 2 ? e.slice(0, 3) : [
			"classic",
			"hierarchy",
			"airy"
		];
	}), [Ne, Pe] = (0, l.useState)(!1), [Fe, Ie] = (0, l.useState)(""), [Le, Re] = (0, l.useState)([]), [ze, Be] = (0, l.useState)(0), [Ve, He] = (0, l.useState)([]), [M, Ue] = (0, l.useState)(null), [N, We] = (0, l.useState)(s?.selection || pe), [Ge, Ke] = (0, l.useState)(null), [qe, Je] = (0, l.useState)("detail"), [Ye, Xe] = (0, l.useState)(s?.backgroundPrompt || ""), [Ze, Qe] = (0, l.useState)(null), [$e, et] = (0, l.useState)(null), [tt, nt] = (0, l.useState)(!0), [rt, it] = (0, l.useState)(!1), [at, ot] = (0, l.useState)(!1), [st, P] = (0, l.useState)(null), [ct, lt] = (0, l.useState)(null), [ut, dt] = (0, l.useState)(() => te(i + "pending", null)), [ft, pt] = (0, l.useState)("");
	(0, l.useEffect)(() => {
		ct !== "pattern" && ct !== "background" && pt("");
	}, [ct]);
	let [mt, ht] = (0, l.useState)(""), [gt, _t] = (0, l.useState)(!1), [vt, yt] = (0, l.useState)(null), [bt, xt] = (0, l.useState)(!1), [St, Ct] = (0, l.useState)(null), [wt, Tt] = (0, l.useState)(0), [F, Et] = (0, l.useState)(null), [Dt, Ot] = (0, l.useState)(null), [kt, At] = (0, l.useState)([]), [jt, Mt] = (0, l.useState)(!1), [Nt, Pt] = (0, l.useState)(!1), [Ft, It] = (0, l.useState)(s?.aiDraftChoice ?? null), [Lt, Rt] = (0, l.useState)(s?.aiDraftReference || null);
	(0, l.useEffect)(() => {
		if (!a || tt || F) return;
		let e = {
			selection: N,
			backgroundPrompt: Ye,
			aiDraftChoice: Ft,
			aiDraftReference: Lt
		};
		u.current = e, S(i + "creationDraft", e);
	}, [
		a,
		N,
		Ye,
		Ft,
		Lt,
		tt,
		F
	]);
	let zt = (0, l.useRef)(null);
	(0, l.useEffect)(() => {
		n && r === "ribbon" || (Ct(null), zt.current = null);
	}, [n, r]);
	let Bt = (0, l.useRef)(!1), Vt = (0, l.useRef)(null), Ht = (0, l.useRef)(null), Ut = (0, l.useRef)(!1), Wt = (0, l.useRef)(null), Gt = (0, l.useRef)(!0), Kt = (0, l.useRef)(null), qt = (0, l.useRef)(null), Jt = (0, l.useRef)(0), I = (0, l.useRef)(null), Yt = (0, l.useRef)(null), Xt = (0, l.useRef)(null), Zt = (0, l.useRef)(0), Qt = (0, l.useRef)("");
	(0, l.useEffect)(() => (Gt.current = !0, () => {
		Gt.current = !1, Wt.current?.abort(), I.current?.abort(), Yt.current?.abort(), se.current?.abort(), Xt.current?.abort(), ++Zt.current;
	}), []);
	let $t = e.role === "admin", en = M?.versions?.find((e) => e.id === M.current_version_id), L = M?.versions?.find((e) => e.id === Ge) || en, tn = !!M?.active_job_id || ee(Ze), nn = ee($e), R = rt || tn || !!ut || gt || !!F, rn = M?.recovery_action === "compose_locally" && !M.current_version_id && !M.versions?.length && !tn && !ut && !F, an = !!L && L.id !== M?.current_version_id, on = st?.downloadVersion && st.downloadVersion !== L?.id ? null : st, sn = (0, l.useRef)(null), cn = (0, l.useRef)(null), ln = L?.snapshot?.output_profile, un = [
		"seamless-unit-v1",
		"seamless-unit-v2",
		"seamless-unit-v3"
	].includes(L?.snapshot.loop?.engine || ""), dn = ln?.width && ln?.height && ln?.dpi ? `${ln.width}×${ln.height}px · ${ln.dpi} DPI · ${(ln.width / ln.dpi * 2.54).toFixed(1)}×${(ln.height / ln.dpi * 2.54).toFixed(1)} cm` : "", fn = (0, l.useMemo)(() => new Map(we.map((e) => [e.id, e])), [we]), pn = (0, l.useMemo)(() => {
		let e = {
			pattern: [],
			background: []
		};
		for (let t of we) e[t.kind].push({
			asset: t,
			query: t.name.toLocaleLowerCase()
		});
		return e;
	}, [we]), z = Ee.find((e) => e.id === N.template_id), mn = _e[z?.mode || ""] || [], hn = z?.mode || "", gn = p(N.asset_ids, hn, N.pattern_roles), _n = Object.values(gn), vn = _n.length > 0 && !_n.includes("main") ? "请至少设置一个主图。" : be(hn, _n.filter((e) => e !== "decoration").length, !0), yn = fn.get(N.background_id), bn = N.asset_ids.map((e, t) => ({
		id: e,
		index: t
	})).filter(({ id: e }) => fn.get(e)?.kind !== "pattern"), xn = !!N.background_id && yn?.kind !== "background", Sn = Object.entries(N.zone_background_refs || {}).filter(([, e]) => fn.get(e)?.kind !== "background").map(([e]) => e), Cn = !!N.border_ref && fn.get(N.border_ref)?.kind !== "pattern", wn = [
		bn.length ? `图案第 ${bn.map(({ index: e }) => e + 1).join("、")} 项` : "",
		xn ? "底图" : "",
		...Sn.map((e) => ge[e] ? `${ge[e]}底纹` : "分区底纹"),
		Cn ? "边饰" : ""
	].filter(Boolean), Tn = wn.length > 0, En = N.asset_ids.length > 0 && !!N.background_id && !!z && !Tn && !E && !vn, Dn = a || !En || R || nn, On = !!en && (JSON.stringify(en.snapshot.asset_refs) !== JSON.stringify(N.asset_ids) || en.snapshot.background_ref !== N.background_id || en.snapshot.template_id !== N.template_id || (en.snapshot.design_style || "classic") !== (N.design_style || "classic") || JSON.stringify(p(en.snapshot.asset_refs, en.snapshot.template_mode, m(en.snapshot))) !== JSON.stringify(gn) || (en.snapshot.border_ref || "") !== (N.border_ref || "") || mn.some((e) => en.snapshot.zone_background_refs?.[e] !== N.zone_background_refs?.[e]) || (en.snapshot.background_tone || "original") !== (N.background_tone || "original") || (en.snapshot.design_density || "balanced") !== (N.design_density || "balanced")), kn = JSON.stringify([
		M?.id,
		en?.id,
		N,
		je,
		n,
		r
	]);
	Qt.current = kn, (0, l.useEffect)(() => (Kn(), () => {
		++Zt.current, Xt.current?.abort();
	}), [kn]);
	let An = Ee.filter((e) => e.enabled || e.id === N.template_id), jn = An.filter((e) => me.has(e.mode)), Mn = An.filter((e) => !me.has(e.mode)), Nn = D?.provider === "test", Pn = Nn ? D?.auth_mode !== "hsd" : D?.ai_ready === !0, Fn = D?.provider === "deepseek_seedream" && D?.ai_ready === !0 && D?.ai_draft_available === !0, In = Fn && Ft === !0, Ln = In && Lt?.mode === z?.mode ? Lt : null, Rn = rt ? "正在提交…" : tn ? "正在生成…" : `${In ? "用 AI " : ""}生成${en || M?.versions?.length ? "新作品" : "首稿"}`;
	function zn(e) {
		return e.id === e.mode && e.version === 1 ? `/static/ribbon/layout-v3/${e.mode}.webp` : e.thumbnail_url;
	}
	function Bn(e) {
		return /* @__PURE__ */ (0, w.jsxs)("div", {
			className: "template-option",
			children: [/* @__PURE__ */ (0, w.jsxs)("button", {
				className: `template-card ${N.template_id === e.id ? "selected" : ""}`,
				disabled: R,
				"aria-pressed": N.template_id === e.id,
				onClick: () => Vn({
					...N,
					template_id: e.id
				}),
				children: [/* @__PURE__ */ (0, w.jsx)(Se, {
					src: zn(e),
					alt: `${e.name}样式图`,
					loading: "lazy",
					decoding: "async",
					quiet: !0
				}), /* @__PURE__ */ (0, w.jsxs)("span", { children: [e.name, N.template_id === e.id && /* @__PURE__ */ (0, w.jsx)(O, {
					name: "check",
					size: 14
				})] })]
			}), N.template_id === e.id && /* @__PURE__ */ (0, w.jsx)("button", {
				type: "button",
				className: "template-example-button",
				"aria-label": `查看${e.name}案例`,
				onClick: () => {
					lt(null), Ct({
						mode: e.mode,
						name: e.name
					});
				},
				children: "查看案例"
			})]
		}, e.id);
	}
	function Vn(e) {
		Kn(), e.template_id !== N.template_id && (Rt(null), delete e.zone_background_refs, delete e.border_ref, e.pattern_roles = Object.fromEntries(Object.entries(e.pattern_roles || {}).filter(([, e]) => e === "decoration")));
		let t = Ee.find((t) => t.id === e.template_id)?.mode || "";
		e.pattern_roles = p(e.asset_ids, t, e.pattern_roles), We(e), S(i + "selection", {
			design_id: qt.current?.id || null,
			base_version_id: qt.current?.current_version_id || null,
			value: e
		});
	}
	function Hn() {
		let e = new Set(bn.map(({ id: e }) => e));
		Vn({
			...N,
			asset_ids: N.asset_ids.filter((t) => !e.has(t)),
			background_id: xn ? "" : N.background_id,
			border_ref: Cn ? void 0 : N.border_ref,
			zone_background_refs: N.zone_background_refs && Object.fromEntries(Object.entries(N.zone_background_refs).filter(([e]) => !Sn.includes(e)))
		});
	}
	async function Un(e) {
		ae(!0);
		try {
			let t = await g("/assets", { signal: e });
			if (!Gt.current || e?.aborted || !Array.isArray(t)) return;
			Te(t), ae(!1);
		} catch (n) {
			if (!Gt.current || e?.aborted) return;
			n instanceof h && n.status === 401 && t();
		}
	}
	function Wn(e, t = !1) {
		let n = Kt.current !== e.current_version_id, r = qt.current;
		if (r?.id === e.id && !r.current_version_id && e.current_version_id && (It(null), Rt(null)), (t || n || qt.current?.id !== e.id) && Kn(), qt.current = e, Ue(e), S(i + "design", e.id), He((t) => [e, ...t.filter((t) => t.id !== e.id)]), t || n) {
			let n = e.versions?.find((t) => t.id === e.current_version_id);
			Je(n && ["ends", "ends_open"].includes(n.snapshot.template_mode) ? "fit" : "detail");
			let r = te(i + "selection", null), a = c.current && u.current ? u.current.selection : t && r?.design_id === e.id && r.base_version_id === e.current_version_id ? r.value : n ? {
				asset_ids: n.snapshot.asset_refs,
				background_id: n.snapshot.background_ref,
				template_id: n.snapshot.template_id,
				zone_background_refs: n.snapshot.zone_background_refs,
				border_ref: n.snapshot.border_ref,
				...n.snapshot.layout_engine === "seamless-unit-v3" ? { pattern_roles: m(n.snapshot) } : {},
				background_tone: n.snapshot.background_tone || "original",
				design_style: n.snapshot.design_style || "classic",
				...[
					"design-rhythm-v1",
					"design-rhythm-v2",
					"seamless-unit-v1",
					"seamless-unit-v2",
					"seamless-unit-v3"
				].includes(n.snapshot.layout_engine || "") ? { design_density: n.snapshot.design_density || "balanced" } : {}
			} : pe;
			We(k(a, n)), Ke(e.current_version_id), Kt.current = e.current_version_id;
		}
		e.active_job && Qe(e.active_job);
	}
	function Gn(e) {
		let t = je.includes(e);
		if (t && je.length <= 2) return;
		let n = t ? je.filter((t) => t !== e) : [...je, e];
		n.length > 3 || (Kn(), Me(n), S(i + "trialStyles", n));
	}
	function Kn() {
		++Zt.current, Xt.current?.abort(), Xt.current = null, Pe(!1), Re([]), Be(0), Ie(""), Ae(null);
	}
	async function qn() {
		if (Xt.current || R || !n || r !== "ribbon" || Tn || E) return;
		if (!N.asset_ids.length || !N.background_id || !N.template_id) {
			Ie("先选择图案、底纹和排版");
			return;
		}
		if (vn) return;
		if (je.length < 2) {
			Ie("至少选择两种风格来对比");
			return;
		}
		let e = [...je], i = new AbortController(), a = ++Zt.current, o = Qt.current;
		Xt.current = i;
		let s = () => !Gt.current || i.signal.aborted || a !== Zt.current || o !== Qt.current;
		Pe(!0), Ie(""), Ae([]), Re(e), Be(0);
		try {
			for (let n of e) {
				if (s()) return;
				try {
					let e = await g("/candidates/one", {
						method: "POST",
						signal: i.signal,
						body: JSON.stringify({
							...N,
							pattern_roles: gn,
							style: n
						})
					});
					if (s()) return;
					if (e.style !== n) throw new h("试排结果与所选风格不一致，请重新试排。", 409);
					Ae((t) => [...t || [], e]);
				} catch (e) {
					if (s()) return;
					if (e instanceof h && e.status === 401) {
						t();
						return;
					}
					if (e instanceof h && e.code === "asset_selection_unavailable") {
						Ae(null), await Un(i.signal);
						break;
					}
					Ie(fe(e));
				}
				s() || Be((e) => e + 1);
			}
		} finally {
			s() || (Xt.current = null, Pe(!1), Re([]));
		}
	}
	async function Jn() {
		let [e, t, n, r] = await Promise.all([
			g("/assets"),
			g("/templates"),
			g("/config"),
			g("/design-styles")
		]);
		Te(e), j(t), ce(n), r.length && Oe(r);
	}
	(0, l.useEffect)(() => {
		let e = !1, n = new AbortController();
		async function r() {
			nt(!0), C("");
			try {
				let t = await Promise.allSettled([
					g("/assets", { signal: n.signal }),
					g("/templates", { signal: n.signal }),
					g("/config", { signal: n.signal }),
					g("/designs?summary=true", { signal: n.signal }),
					g("/design-styles", { signal: n.signal })
				]);
				if (e) return;
				let [r, a, o, s, l] = t;
				r.status === "fulfilled" && (Te(r.value), ae(!1)), a.status === "fulfilled" && j(a.value), o.status === "fulfilled" && ce(o.value), s.status === "fulfilled" && He(s.value), l.status === "fulfilled" && l.value.length && Oe(l.value);
				let d = t.find((e) => e.status === "rejected");
				if (d?.status === "rejected") throw d.reason;
				let f = r.status === "fulfilled" ? r.value : [], p = a.status === "fulfilled" ? a.value : [], m = s.status === "fulfilled" ? s.value : [], _ = te(i + "design", null), v = m.find((e) => e.id === _)?.id || (c.current ? void 0 : m[0]?.id);
				if (v) {
					let t = await g(`/designs/${v}`, { signal: n.signal });
					e || (Wn(t, !0), t.active_job_id && P({
						text: "已恢复作品，正在同步后台任务。离开页面不会中断处理。",
						type: "info"
					}));
				} else {
					let e = te(i + "selection", null);
					We(k(c.current && u.current ? u.current.selection : e?.value || xe(f, p)));
				}
				let y = te(i + "backgroundJob", null);
				if (y) try {
					let t = await g(`/jobs/${y}`, { signal: n.signal });
					e || et(t);
				} catch (t) {
					if (!(t instanceof h) || ![404, 410].includes(t.status)) throw t;
					!e && te(i + "backgroundJob", null) === y && (S(i + "backgroundJob", null), S(i + "backgroundTarget", null), et(null), P({
						text: "上次的底图任务已不可用，请从底图库选择底图。",
						type: "info"
					}));
				}
			} catch (n) {
				e || (C(fe(n)), n instanceof h && n.status === 401 && t());
			} finally {
				e || nt(!1);
			}
		}
		return r(), () => {
			e = !0, n.abort();
		};
	}, [_]), (0, l.useEffect)(() => {
		if (!n || !M?.id && !$e?.id) return;
		let e = new AbortController(), r = Jt.current, a = M?.id, o = () => s || !Gt.current || r !== Jt.current || a !== void 0 && qt.current?.id !== a, s = !1, c = !1, l = async () => {
			if (!(c || document.hidden)) {
				c = !0;
				try {
					if (at && !M?.id && !ee($e) && await g("/config", { signal: e.signal }), M?.id) {
						let t = await g(`/designs/${M.id}`, { signal: e.signal });
						if (o()) return;
						let n = qt.current;
						Wn(t);
						let r = t.active_job_id || n?.active_job_id || Ze?.id;
						if (r) {
							let t = await g(`/jobs/${r}`, { signal: e.signal });
							if (o()) return;
							Qe(t), t.status === "FAILED" && Ze?.status !== "FAILED" && P(t.recovery_action === "compose_locally" ? null : {
								text: t.error || "此次处理未完成，已保存的版本仍可下载。",
								type: "error"
							});
						}
					}
					if ($e && ee($e)) {
						let t = await g(`/jobs/${$e.id}`, { signal: e.signal });
						if (o()) return;
						et(t), t.status === "FAILED" && (S(i + "backgroundJob", null), P({
							text: t.error || "底图未能生成，请重试。",
							type: "error"
						}));
					}
					ot(!1);
				} catch (e) {
					o() || (ot(!0), e instanceof h && e.status === 401 && t());
				} finally {
					c = !1;
				}
			}
		};
		at || l();
		let u = tn || nn || at ? window.setInterval(l, at && !tn && !nn ? 2500 : 1200) : void 0;
		return document.addEventListener("visibilitychange", l), window.addEventListener("focus", l), () => {
			s = !0, e.abort(), clearInterval(u), document.removeEventListener("visibilitychange", l), window.removeEventListener("focus", l);
		};
	}, [
		n,
		at,
		M?.id,
		M?.active_job_id,
		$e?.id,
		$e?.status,
		Ze?.id,
		Ze?.status
	]), (0, l.useEffect)(() => {
		let e = M?.versions.find((e) => e.id === M.current_version_id)?.snapshot;
		if (!e || at || [
			...e.asset_refs,
			e.background_ref,
			...Object.values(e.zone_background_refs || {}),
			...e.border_ref ? [e.border_ref] : []
		].every((e) => we.some((t) => t.id === e))) return;
		let t = new AbortController(), n = Jt.current;
		return g("/assets", { signal: t.signal }).then((e) => {
			!t.signal.aborted && Gt.current && n === Jt.current && Te(e);
		}).catch(() => {
			!t.signal.aborted && n === Jt.current && ot(!0);
		}), () => t.abort();
	}, [M?.current_version_id, at]), (0, l.useEffect)(() => {
		if ($e?.status !== "SUCCEEDED" || !$e.result_asset_id || te(i + "backgroundJob", null) !== $e.id || at) return;
		let e = new AbortController();
		return g("/assets", { signal: e.signal }).then((t) => {
			if (e.signal.aborted || !Gt.current) return;
			Te(t);
			let n = te(i + "backgroundTarget", null), r = t.some((e) => e.id === $e.result_asset_id && e.kind === "background");
			r && (!n || n.design_id === (qt.current?.id || null)) && We((e) => {
				let t = {
					...e,
					background_id: $e.result_asset_id
				};
				return S(i + "selection", {
					design_id: qt.current?.id || null,
					base_version_id: qt.current?.current_version_id || null,
					value: t
				}), t;
			}), S(i + "backgroundJob", null), S(i + "backgroundTarget", null), P(r ? {
				text: "已恢复上次完成的底图。",
				type: "success"
			} : {
				text: "上次生成的底图已不可用，请从底图库重新选择。",
				type: "info"
			});
		}).catch(() => {
			!e.signal.aborted && Gt.current && ot(!0);
		}), () => e.abort();
	}, [
		$e?.id,
		$e?.status,
		at
	]);
	async function Yn(e) {
		let n = /\/refinements$/.test(e.path);
		dt(e), S(i + "pending", e);
		try {
			if (!n && e.path !== "/background-jobs" && !/^\/designs\/[^/]+\/generate$/.test(e.path)) throw dt(null), S(i + "pending", null), new h("这项旧提交无法继续，请刷新作品列表查看已保存结果。", 410);
			let t = e.body.idempotency_key;
			if (n && (typeof t != "string" || !t || !e.designId)) throw new h("这项旧提交缺少恢复信息，请查看已保存作品。", 410);
			let r = n ? await g(`/jobs/by-request/${encodeURIComponent(String(t))}`) : await b(e.path, e.body);
			if (n && (r.kind !== "refine" || r.design_id !== e.designId)) throw new h("旧任务类型或作品不一致，请刷新作品列表查看。", 409);
			if (dt(null), S(i + "pending", null), P(null), e.kind === "background") S(i + "backgroundTarget", { design_id: e.designId || null }), et(r), S(i + "backgroundJob", r.id);
			else if (Qe(r), e.designId) try {
				Wn(await g(`/designs/${e.designId}`));
			} catch {
				ot(!0), P({
					text: "任务已接受，正在等待连接恢复以同步结果。",
					type: "info"
				});
			}
		} catch (r) {
			if (r instanceof h && r.status >= 400 && r.status < 500 && r.status !== 408 && !(n && [
				401,
				403,
				429
			].includes(r.status)) && (dt(null), S(i + "pending", null)), r instanceof h && r.status === 401) {
				t();
				return;
			}
			if (!n && r instanceof h && r.code === "asset_selection_unavailable") {
				P(null), await Un();
				return;
			}
			P({
				text: r instanceof h && r.status >= 400 && r.status < 500 && r.status !== 408 ? /\/refinements$/.test(e.path) && [404, 410].includes(r.status) ? "旧任务不存在或已过期，请查看已保存作品；需要新结果可生成新作品。" : fe(r) : /\/refinements$/.test(e.path) ? "暂时无法读取旧任务状态，请点击“重试读取任务”；不会重新发送图片处理。" : "连接中断，提交结果尚未确认。请点击“恢复提交”，将使用原请求安全查询或继续。",
				type: "error"
			});
		}
	}
	async function Xn(e) {
		if (!Bt.current) {
			Bt.current = !0, it(!0);
			try {
				await e();
			} catch (e) {
				P({
					text: fe(e),
					type: "error"
				});
			} finally {
				Bt.current = !1, it(!1);
			}
		}
	}
	function Zn() {
		let e = {
			selection: N,
			backgroundPrompt: Ye,
			aiDraftChoice: Ft,
			aiDraftReference: Lt
		};
		c.current = !0, u.current = e, o(!0), S(i + "creationDraft", e), S(i + "creationUncertain", !0);
	}
	function Qn() {
		c.current = !1, u.current = null, o(!1), S(i + "creationUncertain", null), S(i + "creationDraft", null);
	}
	async function $n(e) {
		try {
			return await b("/designs", { name: e });
		} catch (e) {
			throw !(e instanceof h) || e.status === 408 || e.status >= 500 ? (Zn(), Error("作品建立结果尚未确认。请从“我的作品”刷新后选择要继续的作品，暂不重复创建。")) : e;
		}
	}
	async function er(e = !1) {
		if (c.current || Dn || e && (!rn || qt.current?.id !== M?.id)) return;
		let t = structuredClone({
			...N,
			pattern_roles: gn
		}), n = !e && In, r = {
			idempotency_key: crypto.randomUUID(),
			...t,
			ai_assisted: n,
			reference_code: n && Ln?.code || null
		};
		await Xn(async () => {
			e && (It(!1), Rt(null));
			let n = M;
			(!n || n.current_version_id || n.versions?.length) && (n = await $n(`丝带设计 ${(/* @__PURE__ */ new Date()).toLocaleDateString("zh-CN")}`), Kt.current = null, Wn(n, !0), We(t), S(i + "selection", {
				design_id: n.id,
				base_version_id: null,
				value: t
			}), Qe(null)), await Yn({
				path: `/designs/${n.id}/generate`,
				body: r,
				kind: "design",
				designId: n.id
			});
		});
	}
	async function tr() {
		!R && en?.parent_version_id && await Xn(async () => {
			Wn(await b(`/designs/${M.id}/rollback`, { expected_version_id: en.id })), Qe(null), P({
				text: "已返回上一保存版本。",
				type: "success"
			});
		});
	}
	function nr(e, t) {
		if (e.defaultPrevented || e.button !== 0 || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
		e.preventDefault();
		let i = sn.current;
		if (!i || !M || L?.id !== t.id || !n || r !== "ribbon") return;
		let a = new URL(e.currentTarget.href);
		a.origin === location.origin && a.pathname === `/api/ribbon/versions/${encodeURIComponent(t.id)}/download` && (a.searchParams.set("frame", "1"), cn.current = {
			url: a.href,
			versionId: t.id,
			designId: M.id
		}, P((e) => e?.downloadVersion ? null : e), i.src = a.href);
	}
	function rr() {
		let e = cn.current, t = sn.current?.contentDocument;
		if (!e || t?.URL !== e.url || (cn.current = null, !n || r !== "ribbon" || qt.current?.id !== e.designId || L?.id !== e.versionId)) return;
		let i = t.body?.textContent?.trim();
		if (!i) return;
		let a = "";
		try {
			let e = JSON.parse(i);
			typeof e?.error == "string" ? a = e.error : typeof e?.detail == "string" && (a = e.detail);
		} catch {}
		P({
			type: "error",
			text: a || "下载未能开始，请稍后重试。",
			downloadVersion: e.versionId
		});
	}
	async function ir() {
		c.current || rt || ut || nn || gt || (Kn(), ++Jt.current, I.current?.abort(), Et(null), await Xn(async () => {
			let e = await $n(`丝带设计 ${Ve.length + 1}`);
			It(null), Rt(null), Kt.current = null, Wn(e, !0), Vn(xe(we, Ee)), Qe(null), P(null), lt(null);
		}));
	}
	async function ar(e) {
		if (rt || ut || nn || gt) return;
		let n = c.current ? u.current : null;
		Kn();
		let r = ++Jt.current;
		I.current?.abort();
		let a = new AbortController();
		I.current = a;
		let o = Ve.find((t) => t.id === e)?.name || "所选作品";
		Et({
			id: e,
			name: o,
			loading: !0
		}), qt.current = null, Ue(null), Ke(null), We(pe), Kt.current = null, Qe(null), It(null), Rt(null), P(null), lt(null);
		try {
			let t = await g(`/designs/${e}`, { signal: a.signal });
			if (!Gt.current || r !== Jt.current || a.signal.aborted) return;
			if (c.current && Qn(), Wn(t, !0), n && !t.current_version_id && !t.versions?.length) {
				let e = k(n.selection);
				We(e), Xe(n.backgroundPrompt), It(n.aiDraftChoice), Rt(n.aiDraftReference), S(i + "selection", {
					design_id: t.id,
					base_version_id: null,
					value: e
				});
			}
			Et(null), Qe(t.active_job || null), ot(!1);
		} catch (n) {
			if (!Gt.current || r !== Jt.current || a.signal.aborted) return;
			Et({
				id: e,
				name: o,
				loading: !1
			}), P({
				text: fe(n),
				type: "error"
			}), n instanceof h && n.status === 401 && t();
		}
	}
	async function or() {
		lt("designs"), Mt(!1), Ot(null), ie(""), se.current?.abort();
		let e = new AbortController();
		se.current = e, ne(!0);
		try {
			let t = await g("/designs?summary=true", { signal: e.signal });
			!e.signal.aborted && Gt.current && He(t);
		} catch (t) {
			!e.signal.aborted && Gt.current && ie(fe(t));
		} finally {
			!e.signal.aborted && Gt.current && ne(!1);
		}
	}
	async function sr() {
		Yt.current?.abort();
		let e = new AbortController();
		Yt.current = e, Pt(!0);
		try {
			let t = await g("/designs?deleted=true&summary=true", { signal: e.signal });
			!e.signal.aborted && Gt.current && At(t);
		} catch (t) {
			!e.signal.aborted && Gt.current && P({
				text: fe(t),
				type: "error"
			});
		} finally {
			!e.signal.aborted && Gt.current && Pt(!1);
		}
	}
	async function cr(e) {
		rt || ut || gt || nn || F?.loading || e.active_job_id || await Xn(async () => {
			await g(`/designs/${e.id}`, { method: "DELETE" }), Gt.current && (Yt.current?.abort(), Pt(!1), He((t) => t.filter((t) => t.id !== e.id)), At((t) => [e, ...t.filter((t) => t.id !== e.id)]), (qt.current?.id === e.id || F?.id === e.id) && (++Jt.current, I.current?.abort(), qt.current = null, Ue(null), Et(null), Ke(null), Kt.current = null, Qe(null), It(null), Rt(null), We(xe(we, Ee)), S(i + "design", null), S(i + "selection", null)), Ot(null), P({
				text: `作品已删除，可在“已删除作品”中恢复；保留 ${D?.retention_hours ?? 50} 小时。`,
				type: "success"
			}));
		});
	}
	async function lr(e) {
		Yt.current?.abort(), Pt(!1), await Xn(async () => {
			let t = await b(`/designs/${e.id}/restore`, {});
			Gt.current && (He((n) => [t, ...n.filter((t) => t.id !== e.id)]), At((t) => t.filter((t) => t.id !== e.id)), P({
				text: "作品已恢复，原有版本仍可查看和下载。",
				type: "success"
			}));
		});
	}
	async function ur() {
		R || nn || (Pn ? await Xn(() => Yn({
			path: "/background-jobs",
			body: {
				idempotency_key: crypto.randomUUID(),
				prompt: Ye.trim()
			},
			kind: "background",
			designId: M?.id
		})) : P({
			text: "AI 服务尚未配置，请联系管理员；仍可使用已有底图生成首稿。",
			type: "info"
		}));
	}
	async function dr(e, n) {
		if (!e?.length || Ut.current || R) return;
		let r = Array.from(e), a = $t && bt;
		Ut.current = !0;
		let o = new AbortController();
		Wt.current = o, _t(!0), yt({
			completed: 0,
			total: r.length
		}), P({
			text: `正在上传第 1 / ${r.length} 张…`,
			type: "info"
		});
		let s = [];
		try {
			for (let [e, t] of r.entries()) {
				if (!Gt.current) return;
				let c = new FormData();
				c.append("file", t), c.append("kind", n), c.append("name", t.name.replace(/\.[^.]+$/, "")), c.append("shared", String(a));
				let l = await g("/assets", {
					method: "POST",
					body: c,
					signal: o.signal
				});
				if (!Gt.current) return;
				s.push(l), Te((e) => e.some((e) => e.id === l.id) ? e.map((e) => e.id === l.id ? l : e) : [...e, l]), We((e) => {
					let t = n === "pattern" ? {
						...e,
						asset_ids: [.../* @__PURE__ */ new Set([...e.asset_ids, l.id])].slice(0, 12)
					} : {
						...e,
						background_id: l.id
					};
					return S(i + "selection", {
						design_id: qt.current?.id || null,
						base_version_id: qt.current?.current_version_id || null,
						value: t
					}), t;
				}), yt({
					completed: s.length,
					total: r.length
				}), e + 1 < r.length && P({
					text: `已上传 ${s.length} / ${r.length} 张，正在上传第 ${e + 2} 张…`,
					type: "info"
				});
			}
			P({
				text: `已上传 ${s.length} 个${n === "pattern" ? "图案" : "底图"}。`,
				type: "success"
			});
		} catch (e) {
			if (!Gt.current) return;
			e instanceof h && e.status === 401 && t();
			let n = e instanceof h ? fe(e) : "本张上传结果尚未确认。请重新载入网页，在素材库查看后再决定是否重传。";
			P({
				text: s.length ? `已上传 ${s.length} 个，其余未完成：${n}` : n,
				type: "error"
			});
		} finally {
			Ut.current = !1, Wt.current = null, Gt.current && (_t(!1), yt(null)), Vt.current && (Vt.current.value = ""), Ht.current && (Ht.current.value = "");
		}
	}
	function fr(e) {
		R || (!N.asset_ids.includes(e) && N.asset_ids.length >= 12 ? P({
			text: "每份设计最多选择 12 个图案。",
			type: "info"
		}) : Vn({
			...N,
			asset_ids: N.asset_ids.includes(e) ? N.asset_ids.filter((t) => t !== e) : [...N.asset_ids, e]
		}));
	}
	(0, l.useEffect)(() => {
		n ? r === "ribbon-admin" && ($t ? lt("admin") : P({
			text: "排版与规格维护仅供管理员使用。",
			type: "error"
		})) : lt(null);
	}, [
		n,
		r,
		$t
	]);
	async function pr(e) {
		await Xn(async () => {
			await g(`/assets/${e.id}`, { method: "DELETE" }), Te((t) => t.filter((t) => t.id !== e.id)), Vn({
				...N,
				asset_ids: N.asset_ids.filter((t) => t !== e.id),
				background_id: N.background_id === e.id ? "" : N.background_id,
				border_ref: N.border_ref === e.id ? void 0 : N.border_ref,
				zone_background_refs: N.zone_background_refs && Object.fromEntries(Object.entries(N.zone_background_refs).filter(([, t]) => t !== e.id))
			});
		});
	}
	let mr = F ? F.loading ? "正在打开作品" : "作品打开失败" : tn ? Ce[Ze?.phase || ""] || Ze?.phase || Ce[Ze?.status || ""] || "正在处理" : en ? "已保存" : En ? "可以生成首稿" : "等待选择素材", hr = (0, l.useMemo)(() => {
		if (ct !== "pattern" && ct !== "background") return [];
		let e = mt.toLocaleLowerCase().trim();
		return e ? pn[ct].filter((t) => t.query.includes(e)).map((e) => e.asset) : pn[ct].map((e) => e.asset);
	}, [
		pn,
		ct,
		mt
	]), gr = Math.max(1, Math.ceil(hr.length / 36)), _r = Math.min(wt, gr - 1), vr = hr.slice(_r * 36, (_r + 1) * 36);
	return (0, l.useEffect)(() => {
		Tt(0);
	}, [ct, mt]), /* @__PURE__ */ (0, w.jsxs)("div", {
		className: "app-shell",
		children: [
			/* @__PURE__ */ (0, w.jsxs)("header", {
				className: "topbar",
				children: [/* @__PURE__ */ (0, w.jsx)(de, {}), /* @__PURE__ */ (0, w.jsxs)("div", {
					className: "header-actions",
					children: [
						/* @__PURE__ */ (0, w.jsxs)("button", {
							className: "secondary",
							disabled: a || rt || !!ut || nn || gt,
							onClick: () => void ir(),
							children: [/* @__PURE__ */ (0, w.jsx)(O, { name: "plus" }), "新建作品"]
						}),
						/* @__PURE__ */ (0, w.jsxs)("button", {
							className: "text-button",
							onClick: () => void or(),
							children: [
								/* @__PURE__ */ (0, w.jsx)(O, { name: "folder" }),
								"我的作品",
								/* @__PURE__ */ (0, w.jsx)("span", {
									className: "count",
									children: Ve.length
								})
							]
						}),
						$t && /* @__PURE__ */ (0, w.jsxs)("button", {
							className: "text-button",
							onClick: () => lt("admin"),
							children: [/* @__PURE__ */ (0, w.jsx)(O, { name: "settings" }), "排版与规格"]
						})
					]
				})]
			}),
			/* @__PURE__ */ (0, w.jsxs)("main", { children: [
				/* @__PURE__ */ (0, w.jsx)("iframe", {
					ref: sn,
					hidden: !0,
					title: "丝带版本下载",
					onLoad: rr
				}),
				D && (Nn || !Pn || D.output_profile?.is_demo) && /* @__PURE__ */ (0, w.jsxs)("div", {
					className: "environment-strip compact-status",
					children: [
						Nn && /* @__PURE__ */ (0, w.jsx)("span", {
							className: en ? void 0 : "test-limit",
							children: "测试模型 · 演示模式（测试替身）"
						}),
						D.output_profile?.is_demo && /* @__PURE__ */ (0, w.jsx)("span", { children: "演示输出 · 未经业务验收" }),
						!Pn && /* @__PURE__ */ (0, w.jsx)("span", { children: "AI 尚未配置，可用已有素材排版。" })
					]
				}),
				on && /* @__PURE__ */ (0, w.jsxs)("div", {
					className: `notice ${on.type}`,
					role: on.type === "error" ? "alert" : "status",
					children: [/* @__PURE__ */ (0, w.jsx)("span", { children: on.text }), /* @__PURE__ */ (0, w.jsx)("button", {
						"aria-label": "关闭提示",
						className: "icon-button",
						onClick: () => P(null),
						children: /* @__PURE__ */ (0, w.jsx)(O, {
							name: "close",
							size: 15
						})
					})]
				}),
				!tt && !y && rn && /* @__PURE__ */ (0, w.jsxs)("div", {
					className: "notice error draft-recovery-notice",
					role: "alert",
					children: [/* @__PURE__ */ (0, w.jsxs)("div", { children: [/* @__PURE__ */ (0, w.jsx)("strong", { children: "AI 搭配结果未通过审核" }), /* @__PURE__ */ (0, w.jsx)("div", { children: "可以用当前图案、底图和排版直接生成。" })] }), /* @__PURE__ */ (0, w.jsx)("button", {
						type: "button",
						className: "secondary small",
						disabled: Dn,
						onClick: () => void er(!0),
						children: "改用本地合成"
					})]
				}),
				!tt && !y && (Tn || E) && /* @__PURE__ */ (0, w.jsxs)("div", {
					className: "notice error asset-selection-notice",
					id: "ribbon-asset-issue",
					role: "alert",
					children: [/* @__PURE__ */ (0, w.jsxs)("div", { children: [/* @__PURE__ */ (0, w.jsx)("strong", { children: "所选素材有变动" }), /* @__PURE__ */ (0, w.jsx)("div", { children: E ? "请刷新素材库，确认当前可用素材。" : `${wn.join("、")}已不可用，请移除或重新选择后再生成。` })] }), /* @__PURE__ */ (0, w.jsxs)("div", {
						className: "asset-selection-actions",
						children: [Tn && !E && /* @__PURE__ */ (0, w.jsx)("button", {
							type: "button",
							className: "secondary small",
							disabled: R || Ne,
							onClick: Hn,
							children: "移除不可用素材"
						}), /* @__PURE__ */ (0, w.jsx)("button", {
							type: "button",
							className: "secondary small",
							disabled: R || Ne,
							onClick: () => void Xn(() => Un()),
							children: "刷新素材库"
						})]
					})]
				}),
				at && /* @__PURE__ */ (0, w.jsx)("div", {
					className: "notice error",
					role: "status",
					children: "连接暂时中断，正在重连。后台任务和已保存版本不会因此重置。"
				}),
				a && /* @__PURE__ */ (0, w.jsxs)("div", {
					className: "notice error",
					role: "alert",
					children: [/* @__PURE__ */ (0, w.jsx)("span", { children: "作品可能已经建立，暂不重复创建。请打开“我的作品”，刷新后选择要继续的作品。" }), /* @__PURE__ */ (0, w.jsx)("button", {
						className: "secondary small",
						onClick: () => void or(),
						children: "查看作品"
					})]
				}),
				ut && /* @__PURE__ */ (0, w.jsxs)("div", {
					className: "notice info",
					children: [/* @__PURE__ */ (0, w.jsx)("span", { children: /\/refinements$/.test(ut.path) ? "有一项旧任务状态尚未读取，只会查询已受理的任务。" : "有一项提交尚未确认；恢复使用原幂等键，不会重复提交已受理的处理。" }), /* @__PURE__ */ (0, w.jsx)("button", {
						className: "secondary small",
						disabled: rt,
						onClick: () => void Xn(() => Yn(ut)),
						children: /\/refinements$/.test(ut.path) ? "重试读取任务" : "恢复提交"
					})]
				}),
				y && /* @__PURE__ */ (0, w.jsxs)("div", {
					className: "notice error",
					role: "alert",
					children: [/* @__PURE__ */ (0, w.jsxs)("span", { children: ["工作台读取未完成：", y] }), /* @__PURE__ */ (0, w.jsx)("button", {
						className: "secondary small",
						onClick: () => v((e) => e + 1),
						children: "重新读取工作台"
					})]
				}),
				tt ? /* @__PURE__ */ (0, w.jsxs)("div", {
					className: "page-loader in-page",
					children: [/* @__PURE__ */ (0, w.jsx)("span", { className: "spinner" }), "正在恢复作品和素材…"]
				}) : /* @__PURE__ */ (0, w.jsxs)("div", {
					className: "workspace-grid",
					children: [/* @__PURE__ */ (0, w.jsxs)("aside", {
						className: "panel source-panel",
						children: [
							/* @__PURE__ */ (0, w.jsx)("div", {
								className: "panel-heading",
								children: /* @__PURE__ */ (0, w.jsxs)("div", { children: [/* @__PURE__ */ (0, w.jsx)("h2", { children: "素材与排版" }), /* @__PURE__ */ (0, w.jsx)("p", {
									className: "panel-sub",
									children: "选择完成后生成，试排可预览当前设置"
								})] })
							}),
							/* @__PURE__ */ (0, w.jsxs)("section", {
								className: "source-section",
								children: [
									/* @__PURE__ */ (0, w.jsxs)("div", {
										className: "section-label",
										children: [/* @__PURE__ */ (0, w.jsxs)("h3", { children: [/* @__PURE__ */ (0, w.jsx)("span", {
											className: "step-index",
											children: "1"
										}), "图案"] }), /* @__PURE__ */ (0, w.jsx)("span", {
											className: "section-meta",
											children: N.asset_ids.length ? `已选 ${N.asset_ids.length}` : "未选"
										})]
									}),
									/* @__PURE__ */ (0, w.jsxs)("div", {
										className: "two-actions",
										children: [/* @__PURE__ */ (0, w.jsxs)("button", {
											className: "secondary",
											disabled: R || gt,
											onClick: () => {
												xt(!1), Vt.current?.click();
											},
											children: [/* @__PURE__ */ (0, w.jsx)(O, {
												name: "upload",
												size: 16
											}), gt ? `上传 ${vt?.completed || 0}/${vt?.total || 0}` : "上传图案"]
										}), /* @__PURE__ */ (0, w.jsxs)("button", {
											className: "secondary",
											disabled: R,
											onClick: () => {
												ht(""), lt("pattern");
											},
											children: [/* @__PURE__ */ (0, w.jsx)(O, {
												name: "folder",
												size: 16
											}), "素材库"]
										})]
									}),
									/* @__PURE__ */ (0, w.jsx)("input", {
										ref: Vt,
										type: "file",
										accept: "image/png,image/jpeg,image/webp",
										multiple: !0,
										hidden: !0,
										onChange: (e) => void dr(e.target.files, "pattern")
									}),
									N.asset_ids.length > 1 && /* @__PURE__ */ (0, w.jsx)("p", {
										className: "pattern-role-help",
										children: "给每张图案选用途。主图按所选排法排列，周围装饰缩小后放入空隙。"
									}),
									N.asset_ids.length ? /* @__PURE__ */ (0, w.jsx)("div", {
										className: "selected-patterns has-pattern-roles",
										children: N.asset_ids.map((e, t) => {
											let n = fn.get(e), r = n?.kind === "pattern" ? n : void 0, i = r?.name || `第 ${t + 1} 个图案`;
											return /* @__PURE__ */ (0, w.jsxs)("div", {
												className: "pattern-tile",
												children: [
													/* @__PURE__ */ (0, w.jsxs)("div", {
														className: "checker",
														children: [r ? /* @__PURE__ */ (0, w.jsx)(Se, {
															src: r.thumbnail_url || r.url,
															alt: r.name,
															decoding: "async"
														}) : /* @__PURE__ */ (0, w.jsx)("span", {
															className: "unavailable-pattern",
															children: "不可用"
														}), /* @__PURE__ */ (0, w.jsx)("button", {
															className: "remove-asset",
															disabled: R,
															"aria-label": `移除${i}`,
															onClick: () => fr(e),
															children: "×"
														})]
													}),
													/* @__PURE__ */ (0, w.jsxs)("span", {
														title: i,
														children: [
															t + 1,
															". ",
															r?.name || "图案"
														]
													}),
													r && /* @__PURE__ */ (0, w.jsx)("select", {
														className: "pattern-role",
														"aria-label": `图案 ${t + 1} 的排版角色`,
														value: gn[e],
														disabled: R,
														onChange: (t) => Vn({
															...N,
															pattern_roles: {
																...gn,
																[e]: t.target.value
															}
														}),
														children: f(hn, gn[e]).map((e) => /* @__PURE__ */ (0, w.jsx)("option", {
															value: e.value,
															children: e.label
														}, e.value))
													})
												]
											}, e);
										})
									}) : /* @__PURE__ */ (0, w.jsxs)("button", {
										className: "empty-patterns",
										disabled: R,
										onClick: () => {
											ht(""), lt("pattern");
										},
										children: [
											/* @__PURE__ */ (0, w.jsx)(O, { name: "plus" }),
											/* @__PURE__ */ (0, w.jsx)("span", { children: "从素材库选择，或上传图案" }),
											/* @__PURE__ */ (0, w.jsx)("small", { children: "支持透明 PNG" })
										]
									})
								]
							}),
							/* @__PURE__ */ (0, w.jsxs)("section", {
								className: "source-section",
								children: [
									/* @__PURE__ */ (0, w.jsxs)("div", {
										className: "section-label",
										children: [/* @__PURE__ */ (0, w.jsxs)("h3", { children: [/* @__PURE__ */ (0, w.jsx)("span", {
											className: "step-index",
											children: "2"
										}), "排版"] }), /* @__PURE__ */ (0, w.jsx)("button", {
											type: "button",
											className: "quiet-link",
											onClick: () => Ct({
												mode: null,
												name: "全部排版案例"
											}),
											children: "全部案例"
										})]
									}),
									z && !me.has(z.mode) && /* @__PURE__ */ (0, w.jsxs)("div", {
										className: "chosen-layout",
										children: [/* @__PURE__ */ (0, w.jsxs)("strong", { children: ["已选：", z.name] }), /* @__PURE__ */ (0, w.jsx)("button", {
											type: "button",
											className: "quiet-link",
											onClick: () => Ct({
												mode: z.mode,
												name: z.name
											}),
											children: "查看案例"
										})]
									}),
									vn && /* @__PURE__ */ (0, w.jsx)("p", {
										className: "layout-selection-issue",
										id: "ribbon-layout-issue",
										role: "alert",
										children: vn
									}),
									/* @__PURE__ */ (0, w.jsx)("div", {
										className: "template-grid",
										children: jn.map(Bn)
									}),
									Mn.length > 0 && /* @__PURE__ */ (0, w.jsx)("div", {
										className: "more-layouts",
										children: /* @__PURE__ */ (0, w.jsxs)("button", {
											type: "button",
											className: "more-layouts-toggle",
											"aria-expanded": ct === "layouts",
											"aria-haspopup": "dialog",
											onClick: () => lt("layouts"),
											children: [/* @__PURE__ */ (0, w.jsxs)("span", { children: [
												"更多排法（",
												Mn.length,
												"）"
											] }), /* @__PURE__ */ (0, w.jsx)("span", {
												"aria-hidden": "true",
												children: "›"
											})]
										})
									}),
									z && (ye[z.mode] || he[z.mode]) && /* @__PURE__ */ (0, w.jsxs)("details", {
										className: "layout-help",
										children: [/* @__PURE__ */ (0, w.jsx)("summary", { children: "这个排法怎么排" }), /* @__PURE__ */ (0, w.jsx)("p", { children: ve[z.mode] || ye[z.mode] || he[z.mode] })]
									}),
									/* @__PURE__ */ (0, w.jsxs)("label", {
										className: "inline-field",
										children: ["画面密度", /* @__PURE__ */ (0, w.jsxs)("select", {
											"aria-label": "画面密度",
											value: N.design_density || "balanced",
											disabled: R,
											onChange: (e) => Vn({
												...N,
												design_density: e.target.value
											}),
											children: [
												/* @__PURE__ */ (0, w.jsx)("option", {
													value: "airy",
													children: "疏朗"
												}),
												/* @__PURE__ */ (0, w.jsx)("option", {
													value: "balanced",
													children: "均衡"
												}),
												/* @__PURE__ */ (0, w.jsx)("option", {
													value: "rich",
													children: "饱满"
												})
											]
										})]
									}),
									/* @__PURE__ */ (0, w.jsxs)("div", {
										className: "style-control",
										role: "group",
										"aria-label": "设计风格",
										children: [
											/* @__PURE__ */ (0, w.jsx)("span", {
												className: "field-label",
												children: "设计风格"
											}),
											/* @__PURE__ */ (0, w.jsx)("div", {
												className: "style-chips",
												children: De.map((e) => /* @__PURE__ */ (0, w.jsx)("button", {
													type: "button",
													disabled: R,
													className: `style-chip ${(N.design_style || "classic") === e.id ? "selected" : ""}`,
													"aria-pressed": (N.design_style || "classic") === e.id,
													title: e.hint,
													onClick: () => Vn({
														...N,
														design_style: e.id
													}),
													children: e.label
												}, e.id))
											}),
											!!De.find((e) => e.id === (N.design_style || "classic"))?.hint && /* @__PURE__ */ (0, w.jsx)("p", {
												className: "style-hint",
												children: De.find((e) => e.id === (N.design_style || "classic"))?.hint
											})
										]
									}),
									/* @__PURE__ */ (0, w.jsxs)("details", {
										className: "trial-box",
										open: !!ke || Ne,
										children: [/* @__PURE__ */ (0, w.jsxs)("summary", { children: [/* @__PURE__ */ (0, w.jsx)("span", { children: "试排对比" }), /* @__PURE__ */ (0, w.jsx)("small", { children: "选 2–3 种风格，本地预览，不调用AI" })] }), /* @__PURE__ */ (0, w.jsxs)("div", {
											className: "trial-body",
											children: [
												/* @__PURE__ */ (0, w.jsx)("div", {
													className: "trial-chips",
													role: "group",
													"aria-label": "试排风格",
													children: De.map((e) => {
														let t = je.includes(e.id);
														return /* @__PURE__ */ (0, w.jsxs)("button", {
															type: "button",
															disabled: R || Ne,
															className: `trial-chip ${t ? "selected" : ""}`,
															"aria-pressed": t,
															onClick: () => Gn(e.id),
															children: [/* @__PURE__ */ (0, w.jsx)("span", {
																className: "trial-check",
																"aria-hidden": "true",
																children: t ? "✓" : ""
															}), e.label]
														}, e.id);
													})
												}),
												/* @__PURE__ */ (0, w.jsx)("button", {
													type: "button",
													className: "primary small",
													disabled: R || Ne || Tn || E || !!vn,
													onClick: () => void qn(),
													children: Ne ? `正在试排 ${ze}/${Le.length}` : `试排这 ${je.length} 种风格`
												}),
												Ne && /* @__PURE__ */ (0, w.jsx)("div", {
													className: "trial-progress",
													role: "progressbar",
													"aria-valuemin": 0,
													"aria-valuemax": Le.length,
													"aria-valuenow": ze,
													children: /* @__PURE__ */ (0, w.jsx)("span", { style: { width: `${Le.length ? ze / Le.length * 100 : 0}%` } })
												}),
												Fe && /* @__PURE__ */ (0, w.jsx)("p", {
													className: "style-hint",
													role: "alert",
													children: Fe
												})
											]
										})]
									}),
									!!ke && /* @__PURE__ */ (0, w.jsxs)("div", {
										className: "candidate-gallery",
										"aria-label": "风格试排",
										children: [
											Le.filter((e) => !ke.some((t) => t.style === e)).map((e) => /* @__PURE__ */ (0, w.jsxs)("figure", {
												className: "candidate-card is-pending",
												"aria-busy": "true",
												children: [/* @__PURE__ */ (0, w.jsx)("div", {
													className: "candidate-skeleton",
													children: /* @__PURE__ */ (0, w.jsx)("span", { className: "spinner tiny" })
												}), /* @__PURE__ */ (0, w.jsxs)("figcaption", { children: [/* @__PURE__ */ (0, w.jsx)("strong", { children: De.find((t) => t.id === e)?.label || e }), /* @__PURE__ */ (0, w.jsx)("span", { children: "正在本地渲染…" })] })]
											}, `pending-${e}`)),
											ke.map((e) => /* @__PURE__ */ (0, w.jsxs)("figure", {
												className: `candidate-card ${(N.design_style || "classic") === e.style ? "selected" : ""}`,
												children: [/* @__PURE__ */ (0, w.jsx)("img", {
													src: e.image,
													alt: `${e.label}试排`
												}), /* @__PURE__ */ (0, w.jsxs)("figcaption", { children: [
													/* @__PURE__ */ (0, w.jsx)("strong", { children: e.label }),
													/* @__PURE__ */ (0, w.jsx)("span", { children: e.rhythm?.repeats_to_length ? `100cm 约 ${e.rhythm.repeats_to_length} 个单元` : `${e.width}px 单元` }),
													/* @__PURE__ */ (0, w.jsx)("button", {
														type: "button",
														className: "secondary small",
														disabled: R,
														onClick: () => {
															Vn({
																...N,
																design_style: e.style
															}), Ae(null);
														},
														children: "用这个风格"
													})
												] })]
											}, e.style)),
											/* @__PURE__ */ (0, w.jsx)("button", {
												type: "button",
												className: "quiet-link close-trial",
												onClick: Kn,
												children: "收起试排"
											})
										]
									})
								]
							}),
							(mn.length > 0 || z?.mode === "bordered") && /* @__PURE__ */ (0, w.jsxs)("details", {
								className: "optional-layers",
								children: [/* @__PURE__ */ (0, w.jsx)("summary", { children: mn.length ? "分区底纹" : "独立边饰" }), (mn.length ? mn : ["border"]).map((e) => {
									let t = e === "border" ? N.border_ref : N.zone_background_refs?.[e];
									return /* @__PURE__ */ (0, w.jsxs)("div", { children: [
										/* @__PURE__ */ (0, w.jsx)("span", { children: ge[e] || "上下边饰" }),
										/* @__PURE__ */ (0, w.jsx)("button", {
											"aria-label": e === "border" ? "选择上下边饰" : `选择${ge[e]}底纹`,
											disabled: R,
											className: "secondary small",
											onClick: () => {
												pt(e), ht(""), lt(e === "border" ? "pattern" : "background");
											},
											children: t && fn.get(t)?.name || (e === "border" ? "选择边饰" : "选择底纹")
										}),
										t && /* @__PURE__ */ (0, w.jsx)("button", {
											disabled: R,
											className: "text-button",
											onClick: () => {
												let t = {
													...N,
													zone_background_refs: { ...N.zone_background_refs }
												};
												e === "border" ? delete t.border_ref : delete t.zone_background_refs[e], Vn(t);
											},
											children: "恢复默认"
										})
									] }, e);
								})]
							}, z?.mode),
							/* @__PURE__ */ (0, w.jsxs)("section", {
								className: "source-section",
								children: [
									/* @__PURE__ */ (0, w.jsxs)("div", {
										className: "section-label",
										children: [/* @__PURE__ */ (0, w.jsxs)("h3", { children: [/* @__PURE__ */ (0, w.jsx)("span", {
											className: "step-index",
											children: "3"
										}), "底图"] }), yn?.is_demo && /* @__PURE__ */ (0, w.jsx)("span", {
											className: "section-meta",
											children: "演示素材"
										})]
									}),
									/* @__PURE__ */ (0, w.jsxs)("div", {
										className: "two-actions",
										children: [/* @__PURE__ */ (0, w.jsxs)("button", {
											className: "secondary",
											disabled: R,
											onClick: () => {
												ht(""), lt("background");
											},
											children: [/* @__PURE__ */ (0, w.jsx)(O, {
												name: "folder",
												size: 16
											}), "底图库"]
										}), /* @__PURE__ */ (0, w.jsxs)("button", {
											className: "secondary",
											disabled: R || nn || !Pn,
											onClick: () => void ur(),
											children: [nn ? /* @__PURE__ */ (0, w.jsx)("span", { className: "spinner tiny" }) : /* @__PURE__ */ (0, w.jsx)(O, {
												name: "spark",
												size: 16
											}), Nn ? "生成测试底图" : "AI 生成底图"]
										})]
									}),
									/* @__PURE__ */ (0, w.jsxs)("details", {
										className: "background-prompt-box",
										children: [
											/* @__PURE__ */ (0, w.jsxs)("summary", { children: ["写一句底图要求", /* @__PURE__ */ (0, w.jsx)("small", { children: "可不填" })] }),
											/* @__PURE__ */ (0, w.jsx)("textarea", {
												id: "background-prompt",
												className: "background-prompt",
												value: Ye,
												onChange: (e) => Xe(e.target.value),
												maxLength: 2e3,
												rows: 2,
												disabled: R || nn || !Pn,
												placeholder: "例如：浅蓝色细条纹，不要文字。",
												"aria-describedby": Pn ? void 0 : "background-ai-unavailable"
											}),
											!Pn && /* @__PURE__ */ (0, w.jsx)("p", {
												className: "model-help",
												id: "background-ai-unavailable",
												children: "AI 尚未配置，仍可从底图库选图。"
											})
										]
									}),
									yn?.kind === "background" ? /* @__PURE__ */ (0, w.jsxs)("div", {
										className: "background-selected",
										children: [
											/* @__PURE__ */ (0, w.jsx)(Se, {
												src: yn.thumbnail_url || yn.url,
												alt: "选中的底图",
												loading: "lazy",
												decoding: "async"
											}),
											/* @__PURE__ */ (0, w.jsxs)("div", { children: [/* @__PURE__ */ (0, w.jsx)("strong", { children: yn.name }), /* @__PURE__ */ (0, w.jsx)("small", { children: yn.source === "upload" ? "已上传" : "已选择" })] }),
											/* @__PURE__ */ (0, w.jsx)(O, {
												name: "check",
												size: 16
											})
										]
									}) : /* @__PURE__ */ (0, w.jsx)("div", {
										className: "empty-background",
										children: "选择底图，为图案定下基调"
									}),
									nn && /* @__PURE__ */ (0, w.jsxs)("p", {
										className: "microcopy",
										children: [Nn ? "正在生成测试底图…" : "AI 正在生成底图…", "可离开后恢复。"]
									}),
									/* @__PURE__ */ (0, w.jsxs)("label", {
										className: "inline-field",
										children: ["底纹处理", /* @__PURE__ */ (0, w.jsxs)("select", {
											"aria-label": "底纹处理",
											value: N.background_tone || "soft",
											disabled: R || nn,
											onChange: (e) => Vn({
												...N,
												background_tone: e.target.value
											}),
											children: [
												/* @__PURE__ */ (0, w.jsx)("option", {
													value: "original",
													children: "保持原色"
												}),
												/* @__PURE__ */ (0, w.jsx)("option", {
													value: "soft",
													children: "柔和，突出主图"
												}),
												/* @__PURE__ */ (0, w.jsx)("option", {
													value: "quiet",
													children: "更淡，图案为主"
												})
											]
										})]
									})
								]
							}),
							en && On && /* @__PURE__ */ (0, w.jsx)("div", {
								className: "selection-warning",
								children: "选择已更改，点击“生成新作品”保存结果。"
							})
						]
					}), /* @__PURE__ */ (0, w.jsxs)("section", {
						className: "center-column",
						children: [/* @__PURE__ */ (0, w.jsxs)("div", {
							className: "panel preview-panel",
							children: [
								/* @__PURE__ */ (0, w.jsxs)("div", {
									className: "panel-heading",
									children: [/* @__PURE__ */ (0, w.jsx)("div", { children: /* @__PURE__ */ (0, w.jsx)("h2", { children: F?.name || M?.name || "设计预览" }) }), tn && /* @__PURE__ */ (0, w.jsxs)("span", {
										className: "state-pill working",
										children: [/* @__PURE__ */ (0, w.jsx)("span", { className: "status-dot" }), mr]
									})]
								}),
								/* @__PURE__ */ (0, w.jsxs)("div", {
									className: "generate-area",
									children: [
										/* @__PURE__ */ (0, w.jsxs)("div", {
											className: "workspace-actions",
											children: [/* @__PURE__ */ (0, w.jsxs)("button", {
												className: "primary generation-button",
												disabled: Dn,
												"aria-describedby": Tn || E ? "ribbon-asset-issue" : vn ? "ribbon-layout-issue" : void 0,
												onClick: () => void er(),
												children: [
													tn ? /* @__PURE__ */ (0, w.jsx)("span", { className: "spinner tiny" }) : /* @__PURE__ */ (0, w.jsx)(O, { name: "spark" }),
													Rn,
													/* @__PURE__ */ (0, w.jsx)(O, {
														name: "arrow",
														size: 16
													})
												]
											}), L && /* @__PURE__ */ (0, w.jsxs)("div", {
												className: "result-actions",
												children: [!!en?.parent_version_id && /* @__PURE__ */ (0, w.jsxs)("button", {
													className: "secondary",
													disabled: R,
													onClick: () => void tr(),
													children: [/* @__PURE__ */ (0, w.jsx)(O, {
														name: "back",
														size: 17
													}), "回退上一版"]
												}), /* @__PURE__ */ (0, w.jsxs)("a", {
													className: "secondary",
													href: L.download_url,
													download: !0,
													onClick: (e) => nr(e, L),
													children: [/* @__PURE__ */ (0, w.jsx)(O, {
														name: "download",
														size: 17
													}), an ? "下载所选版本" : un ? "下载循环单元" : "下载当前图"]
												})]
											})]
										}),
										!F && Fn && /* @__PURE__ */ (0, w.jsxs)("div", {
											className: "ai-draft-options",
											children: [/* @__PURE__ */ (0, w.jsxs)("label", { children: [/* @__PURE__ */ (0, w.jsx)("input", {
												type: "checkbox",
												checked: In,
												disabled: R || nn,
												onChange: (e) => {
													It(e.target.checked), e.target.checked || Rt(null);
												}
											}), "AI搭配底纹与装饰"] }), In ? /* @__PURE__ */ (0, w.jsxs)(w.Fragment, { children: [/* @__PURE__ */ (0, w.jsx)("p", { children: "AI 根据配色与排版生成底纹，人物和文字使用原图排版。选择参考案例时会将案例图发送给 Seedream。" }), Ln ? /* @__PURE__ */ (0, w.jsxs)("div", {
												className: "ai-draft-reference",
												children: [/* @__PURE__ */ (0, w.jsxs)("span", { children: ["参考案例：", /* @__PURE__ */ (0, w.jsx)("strong", { children: Ln.code })] }), /* @__PURE__ */ (0, w.jsx)("button", {
													type: "button",
													disabled: R,
													onClick: () => Rt(null),
													children: "取消案例参考"
												})]
											}) : /* @__PURE__ */ (0, w.jsx)("button", {
												type: "button",
												className: "ai-reference-picker",
												disabled: R || !z,
												onClick: () => Ct({
													mode: z?.mode || null,
													name: z?.name || "全部排版案例"
												}),
												children: "选择案例参考"
											})] }) : /* @__PURE__ */ (0, w.jsx)("p", { children: "直接用所选图案和底图排版。" })]
										}),
										/* @__PURE__ */ (0, w.jsx)("small", { children: N.asset_ids.length ? N.template_id ? N.background_id ? vn || (en ? "按当前选择生成独立作品。" : "按当前选择生成作品") : "请选择或生成底图" : "请选择一种排版模式" : "请先选择至少一个图案" })
									]
								}),
								/* @__PURE__ */ (0, w.jsxs)("div", {
									className: `preview-stage ${L ? "is-filled" : "is-empty"}`,
									children: [
										/* @__PURE__ */ (0, w.jsxs)("div", {
											className: "stage-topline",
											children: [/* @__PURE__ */ (0, w.jsx)("span", { children: L ? `V${L.sequence} · ${x(L)}` : "你的设计画布" }), L && /* @__PURE__ */ (0, w.jsx)("span", { children: L.id === M?.current_version_id ? "当前版本" : "历史版本" })]
										}),
										F ? /* @__PURE__ */ (0, w.jsx)("div", {
											className: "empty-canvas design-loading",
											role: "status",
											"aria-live": "polite",
											children: F.loading ? /* @__PURE__ */ (0, w.jsxs)(w.Fragment, { children: [
												/* @__PURE__ */ (0, w.jsx)("span", { className: "spinner" }),
												/* @__PURE__ */ (0, w.jsx)("h3", { children: "正在打开作品…" }),
												/* @__PURE__ */ (0, w.jsx)("p", { children: "正在读取所选作品的版本和素材。" })
											] }) : /* @__PURE__ */ (0, w.jsxs)(w.Fragment, { children: [
												/* @__PURE__ */ (0, w.jsx)("h3", { children: "作品打开失败" }),
												/* @__PURE__ */ (0, w.jsx)("p", { children: "请重试，或从“我的作品”选择其他作品。" }),
												/* @__PURE__ */ (0, w.jsx)("button", {
													className: "secondary",
													onClick: () => void ar(F.id),
													children: "重试打开作品"
												})
											] })
										}) : L && un ? /* @__PURE__ */ (0, w.jsx)(A, {
											version: L,
											sizeLabel: dn
										}, `${M?.id}:${L.id}`) : L ? /* @__PURE__ */ (0, w.jsxs)(w.Fragment, { children: [/* @__PURE__ */ (0, w.jsx)("div", {
											className: `ribbon-display ${qe}`,
											children: /* @__PURE__ */ (0, w.jsx)(Se, {
												decoding: "async",
												src: qe === "detail" && L.view_url || L.preview_url,
												alt: `${x(L)}的设计预览`
											}, `${M?.id}:${L.id}:${qe}`)
										}), /* @__PURE__ */ (0, w.jsxs)("div", {
											className: "ribbon-tools",
											children: [
												/* @__PURE__ */ (0, w.jsxs)("div", {
													className: "ribbon-zoom",
													role: "group",
													"aria-label": "预览缩放",
													children: [/* @__PURE__ */ (0, w.jsx)("button", {
														type: "button",
														className: qe === "detail" ? "is-active" : "",
														"aria-pressed": qe === "detail",
														onClick: () => Je("detail"),
														children: "细节"
													}), /* @__PURE__ */ (0, w.jsx)("button", {
														type: "button",
														className: qe === "fit" ? "is-active" : "",
														"aria-pressed": qe === "fit",
														onClick: () => Je("fit"),
														children: "整条"
													})]
												}),
												/* @__PURE__ */ (0, w.jsx)("span", {
													className: "ribbon-metrics",
													children: dn
												}),
												/* @__PURE__ */ (0, w.jsx)("span", {
													className: "ribbon-hint",
													children: qe === "detail" ? "左右拖动查看整条" : ""
												})
											]
										})] }) : /* @__PURE__ */ (0, w.jsxs)("div", {
											className: "empty-canvas",
											children: [/* @__PURE__ */ (0, w.jsx)("h3", { children: "首稿预览" }), z && /* @__PURE__ */ (0, w.jsxs)("div", {
												className: "template-peek",
												children: [/* @__PURE__ */ (0, w.jsx)(Se, {
													src: zn(z),
													alt: "当前排版参考",
													quiet: !0
												}), /* @__PURE__ */ (0, w.jsxs)("span", { children: [z.name, " · 排版参考"] })]
											})]
										}),
										tn && /* @__PURE__ */ (0, w.jsxs)("div", {
											className: "processing-overlay",
											role: "status",
											children: [
												/* @__PURE__ */ (0, w.jsx)("span", { className: "spinner" }),
												/* @__PURE__ */ (0, w.jsx)("strong", { children: Ce[Ze?.phase || ""] || Ze?.phase || "正在处理设计…" }),
												/* @__PURE__ */ (0, w.jsx)("span", { children: "完成后自动更新，已有版本仍可下载" })
											]
										})
									]
								}),
								L ? /* @__PURE__ */ (0, w.jsxs)(w.Fragment, { children: [(an || L.provider === "test") && /* @__PURE__ */ (0, w.jsx)("div", {
									className: "preview-caption",
									children: /* @__PURE__ */ (0, w.jsx)("span", { children: an ? "正在查看历史保存版本" : "测试模式结果" })
								}), an && /* @__PURE__ */ (0, w.jsxs)("div", {
									className: "history-hint",
									children: ["历史预览不改变当前版本。", /* @__PURE__ */ (0, w.jsx)("button", {
										onClick: () => Ke(M.current_version_id),
										children: "返回当前版本"
									})]
								})] }) : null
							]
						}), !!M?.versions?.length && /* @__PURE__ */ (0, w.jsxs)("details", {
							className: "panel history-panel",
							children: [/* @__PURE__ */ (0, w.jsxs)("summary", {
								className: "history-heading",
								children: [
									"版本记录（",
									M.versions.length,
									"）"
								]
							}), M?.versions?.length ? /* @__PURE__ */ (0, w.jsx)("div", {
								className: "version-grid",
								children: M.versions.map((e) => /* @__PURE__ */ (0, w.jsxs)("button", {
									className: `version-card ${e.id === L?.id ? "selected" : ""}`,
									onClick: () => Ke(e.id),
									"aria-pressed": e.id === L?.id,
									children: [
										/* @__PURE__ */ (0, w.jsx)(Se, {
											src: e.preview_url,
											loading: "lazy",
											decoding: "async",
											alt: `${x(e)}缩略图`
										}),
										/* @__PURE__ */ (0, w.jsxs)("div", { children: [/* @__PURE__ */ (0, w.jsx)("strong", { children: x(e) }), e.id === M.current_version_id ? /* @__PURE__ */ (0, w.jsx)("span", {
											className: "tiny-pill",
											children: "当前"
										}) : /* @__PURE__ */ (0, w.jsxs)("small", { children: ["V", e.sequence] })] }),
										/* @__PURE__ */ (0, w.jsx)("small", {
											className: "version-parent",
											children: e.parent_version_id ? `基于 V${M.versions.find((t) => t.id === e.parent_version_id)?.sequence ?? "?"}` : "初始版本"
										})
									]
								}, e.id))
							}) : /* @__PURE__ */ (0, w.jsxs)("div", {
								className: "empty-history",
								children: [
									/* @__PURE__ */ (0, w.jsx)("span", { className: "history-line" }),
									/* @__PURE__ */ (0, w.jsx)("span", { children: "生成首稿后，版本将保存在这里" }),
									/* @__PURE__ */ (0, w.jsx)("span", { className: "history-line" })
								]
							})]
						}, M.id)]
					})]
				}),
				/* @__PURE__ */ (0, w.jsx)("footer", {
					className: "page-footer",
					children: /* @__PURE__ */ (0, w.jsxs)("span", { children: [
						"个人作品与素材保留 ",
						D?.retention_hours ?? 50,
						" 小时，请及时下载。"
					] })
				})
			] }),
			ct === "layouts" && /* @__PURE__ */ (0, w.jsxs)(ue, {
				title: "选择排版模式",
				onClose: () => lt(null),
				wide: !0,
				className: "layout-picker-modal",
				children: [
					/* @__PURE__ */ (0, w.jsx)("p", {
						className: "muted library-note",
						children: "选择排法后点击完成。案例只作排版参考，正式规格由内部配置决定。"
					}),
					/* @__PURE__ */ (0, w.jsx)("div", {
						className: "layout-picker-grid template-grid",
						children: An.map(Bn)
					}),
					/* @__PURE__ */ (0, w.jsxs)("div", {
						className: "modal-footer",
						children: [/* @__PURE__ */ (0, w.jsxs)("span", { children: ["已选：", z?.name || "尚未选择排版"] }), /* @__PURE__ */ (0, w.jsxs)("button", {
							className: "primary",
							onClick: () => lt(null),
							children: ["完成选择", /* @__PURE__ */ (0, w.jsx)(O, {
								name: "check",
								size: 16
							})]
						})]
					})
				]
			}),
			St && n && r === "ribbon" && /* @__PURE__ */ (0, w.jsx)(ue, {
				title: St.mode ? `${St.name} · 案例` : "全部排版案例",
				onClose: () => Ct(null),
				wide: !0,
				className: "layout-examples-modal",
				children: /* @__PURE__ */ (0, w.jsx)(le, {
					mode: St.mode,
					cache: zt,
					onUnauthorized: t,
					onViewAll: () => Ct({
						mode: null,
						name: "全部排版案例"
					}),
					referenceMode: z?.mode,
					legacyLayout: !1,
					onChooseReference: In && !R && !nn ? (e) => {
						z && d(e, z.mode) && (Rt({
							code: e.code,
							mode: z.mode
						}), Ct(null));
					} : void 0
				})
			}),
			(ct === "pattern" || ct === "background") && /* @__PURE__ */ (0, w.jsxs)(ue, {
				title: ft === "border" ? "选择边饰" : ft ? ge[ft] + "底纹" : ct === "pattern" ? "图案素材库" : "底图素材库",
				onClose: () => lt(null),
				wide: !0,
				className: "asset-library-modal",
				children: [
					/* @__PURE__ */ (0, w.jsxs)("div", {
						className: "library-toolbar",
						children: [/* @__PURE__ */ (0, w.jsx)("input", {
							"aria-label": "搜索素材",
							placeholder: "搜索素材名称…",
							value: mt,
							onChange: (e) => ht(e.target.value)
						}), !ft && /* @__PURE__ */ (0, w.jsxs)("label", {
							className: `secondary upload-label ${gt ? "disabled" : ""}`,
							children: [
								/* @__PURE__ */ (0, w.jsx)(O, { name: "upload" }),
								gt ? `上传 ${vt?.completed || 0}/${vt?.total || 0}` : "上传素材",
								/* @__PURE__ */ (0, w.jsx)("input", {
									ref: Ht,
									type: "file",
									accept: "image/png,image/jpeg,image/webp",
									multiple: !0,
									hidden: !0,
									disabled: gt || R,
									onChange: (e) => void dr(e.target.files, ct)
								})
							]
						})]
					}),
					$t && /* @__PURE__ */ (0, w.jsxs)("label", {
						className: "checkbox-line",
						children: [/* @__PURE__ */ (0, w.jsx)("input", {
							type: "checkbox",
							checked: bt,
							disabled: R,
							onChange: (e) => xt(e.target.checked)
						}), "上传为共享素材，供所有账号使用"]
					}),
					/* @__PURE__ */ (0, w.jsxs)("p", {
						className: "muted library-note",
						children: [
							ct === "pattern" ? "可选择多个已处理好的图案。" : "选择一种底图，作为设计背景。",
							" ",
							"标记“演示”的素材仅供联调。"
						]
					}),
					/* @__PURE__ */ (0, w.jsx)("div", {
						className: "library-grid",
						children: vr.map((e) => {
							let t = ft ? (ft === "border" ? N.border_ref : N.zone_background_refs?.[ft]) === e.id : ct === "pattern" ? N.asset_ids.includes(e.id) : N.background_id === e.id;
							return /* @__PURE__ */ (0, w.jsxs)("div", {
								className: "library-item",
								children: [/* @__PURE__ */ (0, w.jsxs)("button", {
									className: `library-card ${t ? "selected" : ""}`,
									disabled: R,
									"aria-pressed": t,
									onClick: () => ft === "border" ? Vn({
										...N,
										border_ref: e.id
									}) : ft ? Vn({
										...N,
										zone_background_refs: {
											...N.zone_background_refs,
											[ft]: e.id
										}
									}) : ct === "pattern" ? fr(e.id) : Vn({
										...N,
										background_id: e.id
									}),
									children: [
										/* @__PURE__ */ (0, w.jsxs)("div", {
											className: `library-image ${ct === "pattern" ? "checker" : ""}`,
											children: [/* @__PURE__ */ (0, w.jsx)(Se, {
												src: e.thumbnail_url || e.url,
												alt: e.name,
												loading: "lazy",
												decoding: "async"
											}), t && /* @__PURE__ */ (0, w.jsx)("span", {
												className: "check-mark",
												children: /* @__PURE__ */ (0, w.jsx)(O, {
													name: "check",
													size: 14
												})
											})]
										}),
										/* @__PURE__ */ (0, w.jsx)("strong", { children: e.name }),
										/* @__PURE__ */ (0, w.jsxs)("span", { children: [e.is_demo ? "演示 · " : "", e.shared ? "共享素材" : "私有素材"] })
									]
								}), (!e.shared || $t) && /* @__PURE__ */ (0, w.jsx)("button", {
									className: "hide-asset",
									disabled: R,
									onClick: () => void pr(e),
									children: "从素材库移除"
								})]
							}, e.id);
						})
					}),
					!hr.length && /* @__PURE__ */ (0, w.jsx)("div", {
						className: "empty-library",
						children: "没有找到素材，可上传新的图案或底图。"
					}),
					hr.length > 36 && /* @__PURE__ */ (0, w.jsxs)("nav", {
						className: "library-pagination",
						"aria-label": "素材分页",
						children: [
							/* @__PURE__ */ (0, w.jsx)("button", {
								className: "secondary small",
								disabled: _r === 0,
								onClick: () => Tt(_r - 1),
								children: "上一页"
							}),
							/* @__PURE__ */ (0, w.jsxs)("span", {
								role: "status",
								children: [
									"第 ",
									_r + 1,
									" / ",
									gr,
									" 页 · 共 ",
									hr.length,
									" 项"
								]
							}),
							/* @__PURE__ */ (0, w.jsx)("button", {
								className: "secondary small",
								disabled: _r + 1 >= gr,
								onClick: () => Tt(_r + 1),
								children: "下一页"
							})
						]
					}),
					/* @__PURE__ */ (0, w.jsxs)("div", {
						className: "modal-footer",
						children: [/* @__PURE__ */ (0, w.jsx)("span", { children: ft ? ft === "border" ? "选择一个完整边饰" : "选择该区域的底纹" : ct === "pattern" ? `已选 ${N.asset_ids.length} 个图案` : yn ? `已选：${yn.name}` : "尚未选择底图" }), /* @__PURE__ */ (0, w.jsxs)("button", {
							className: "primary",
							onClick: () => lt(null),
							children: ["完成选择", /* @__PURE__ */ (0, w.jsx)(O, {
								name: "check",
								size: 16
							})]
						})]
					})
				]
			}),
			ct === "designs" && /* @__PURE__ */ (0, w.jsxs)(ue, {
				title: "我的作品",
				onClose: () => {
					lt(null), Ot(null);
				},
				wide: !0,
				className: "design-library-modal",
				children: [
					/* @__PURE__ */ (0, w.jsxs)("div", {
						className: "design-list-tabs",
						role: "group",
						"aria-label": "作品列表",
						children: [/* @__PURE__ */ (0, w.jsx)("button", {
							className: jt ? "" : "selected",
							onClick: () => {
								Mt(!1), Ot(null);
							},
							children: "我的作品"
						}), /* @__PURE__ */ (0, w.jsx)("button", {
							className: jt ? "selected" : "",
							onClick: () => {
								Mt(!0), Ot(null), sr();
							},
							children: "已删除作品"
						})]
					}),
					Dt && /* @__PURE__ */ (0, w.jsxs)("div", {
						className: "delete-design-confirm",
						role: "alert",
						children: [/* @__PURE__ */ (0, w.jsxs)("p", { children: [
							"删除“",
							Dt.name,
							"”？删除后保留 ",
							D?.retention_hours ?? 50,
							" 小时，可恢复；已有下载仍绑定原版本。"
						] }), /* @__PURE__ */ (0, w.jsxs)("div", { children: [/* @__PURE__ */ (0, w.jsx)("button", {
							className: "secondary small",
							disabled: rt,
							onClick: () => Ot(null),
							children: "取消"
						}), /* @__PURE__ */ (0, w.jsx)("button", {
							className: "danger-button",
							disabled: rt,
							onClick: () => void cr(Dt),
							children: "确认删除"
						})] })]
					}),
					T && !jt && /* @__PURE__ */ (0, w.jsx)("p", {
						role: "status",
						children: "正在更新作品列表…"
					}),
					re && !jt && /* @__PURE__ */ (0, w.jsxs)("div", {
						className: "notice error",
						role: "alert",
						children: [/* @__PURE__ */ (0, w.jsx)("span", { children: re }), /* @__PURE__ */ (0, w.jsx)("button", {
							className: "secondary small",
							onClick: () => void or(),
							children: "重试读取作品"
						})]
					}),
					Nt && jt && /* @__PURE__ */ (0, w.jsx)("p", {
						role: "status",
						children: "正在读取已删除作品…"
					}),
					/* @__PURE__ */ (0, w.jsx)("div", {
						className: "design-library",
						children: (jt ? kt : Ve).map((e) => /* @__PURE__ */ (0, w.jsxs)("div", {
							className: "design-list-row",
							children: [/* @__PURE__ */ (0, w.jsxs)("button", {
								disabled: rt || !!ut || nn || gt,
								className: `design-list-item ${e.id === M?.id ? "selected" : ""}`,
								onClick: () => jt ? void lr(e) : void ar(e.id),
								"aria-label": jt ? `恢复${e.name}` : void 0,
								children: [
									/* @__PURE__ */ (0, w.jsx)("span", {
										className: "design-list-icon",
										children: /* @__PURE__ */ (0, w.jsx)(O, {
											name: "folder",
											size: 23
										})
									}),
									/* @__PURE__ */ (0, w.jsxs)("div", { children: [/* @__PURE__ */ (0, w.jsx)("strong", { children: e.name }), /* @__PURE__ */ (0, w.jsx)("small", { children: e.current_version_id ? "已有保存版本" : "尚未生成首稿" })] }),
									e.active_job_id && /* @__PURE__ */ (0, w.jsx)("span", {
										className: "tiny-pill",
										children: "处理中"
									}),
									jt ? /* @__PURE__ */ (0, w.jsx)("span", { children: "恢复" }) : /* @__PURE__ */ (0, w.jsx)(O, { name: "arrow" })
								]
							}), !jt && /* @__PURE__ */ (0, w.jsx)("button", {
								type: "button",
								className: "delete-design-button",
								"aria-label": `删除${e.name}`,
								title: e.active_job_id ? "作品正在处理，完成后可删除" : `删除${e.name}`,
								disabled: rt || !!ut || gt || nn || !!F?.loading || !!e.active_job_id,
								onClick: () => Ot(e),
								children: "删除"
							})]
						}, e.id))
					}),
					!(jt ? kt : Ve).length && !Nt && /* @__PURE__ */ (0, w.jsx)("div", {
						className: "empty-library",
						children: jt ? "没有可恢复的已删除作品。" : "你的第一份作品，即将从这里开始。"
					}),
					/* @__PURE__ */ (0, w.jsxs)("div", {
						className: "modal-footer",
						children: [/* @__PURE__ */ (0, w.jsx)("span", { children: jt ? `删除后保留 ${D?.retention_hours ?? 50} 小时，可恢复` : "作品与版本会自动保存" }), /* @__PURE__ */ (0, w.jsxs)("button", {
							className: "primary",
							disabled: a || rt || !!ut || nn || gt,
							onClick: () => void ir(),
							children: [/* @__PURE__ */ (0, w.jsx)(O, { name: "plus" }), "新建作品"]
						})]
					})
				]
			}),
			ct === "admin" && $t && /* @__PURE__ */ (0, w.jsx)(oe, {
				onClose: () => lt(null),
				onChanged: Jn
			})
		]
	});
}
// src/styles.css?inline
var Ee = ":host{color:#233d35;font-synthesis:none;--green:#215b4d;--deep:#163d33;--pale:#edf3e9;--line:#e3e9e2;--muted:#839087;--gold:#b7a66a;--radius:16px;background:#f7f8f4;min-width:0;font-family:Noto Sans SC,Microsoft YaHei,sans-serif;font-size:14px;font-weight:400;line-height:1.55;display:block;container-type:inline-size}*{box-sizing:border-box}.app-shell{min-width:0;margin:0}button,input,textarea,select{font:inherit}button,a,input,textarea,select{-webkit-tap-highlight-color:transparent}button{cursor:pointer}button:disabled{cursor:not-allowed;opacity:.45}button,a{transition:background .16s,border-color .16s,box-shadow .16s,transform .16s}button:focus-visible,a:focus-visible,input:focus-visible,textarea:focus-visible,select:focus-visible{outline-offset:3px;outline:3px solid #a6c6a8}button{color:inherit}a{color:inherit;text-decoration:none}img{max-width:100%;display:block}h1,h2,h3,p{margin:0}h1,h2,h3{font-weight:650}h3{font-size:14px}button svg,a svg{flex-shrink:0}input,textarea,select{width:100%;color:var(--deep);background:#fff;border:1px solid #dfe6df;border-radius:8px;padding:11px 12px}input:focus,textarea:focus,select:focus{border-color:#7ba28c;outline:none}textarea{resize:vertical}input[type=checkbox]{width:15px;height:15px;accent-color:var(--green)}small{font-size:11px}.muted{color:var(--muted)}.microcopy{color:#7c8a80;font-size:11px;line-height:1.8}.eyebrow,.step-label{letter-spacing:1.9px;color:#94a395;font-size:10px;font-weight:500}.primary,.secondary,.text-button,.icon-button{white-space:nowrap;border:0;border-radius:8px;justify-content:center;align-items:center;gap:8px;font-weight:550;display:inline-flex}.primary{background:var(--green);color:#fff;border:1px solid var(--green);padding:13px 22px}.primary:hover:not(:disabled){background:#174b3f;box-shadow:0 4px 14px #184f3c16}.secondary{background:#fff;border:1px solid #dce4dc;padding:10px 16px;font-size:12px}.secondary:hover:not(:disabled){background:#fafcf8;border-color:#8fae99}.text-button{background:0 0;padding:7px;font-size:12px}.text-button:hover{background:#edf1e9}.icon-button{color:#7b8980;background:0 0;flex-shrink:0;width:32px;height:32px}.icon-button:hover{color:var(--green);background:#e9f0e5}.full{width:100%}.small{padding:7px 11px;font-size:11px}.tiny-pill{color:#52735b;white-space:nowrap;background:#edf3e9;border-radius:4px;padding:2px 6px;font-size:10px}.outline-pill{color:#8b8e72;white-space:nowrap;border:1px solid #dddfcf;border-radius:4px;padding:3px 9px;font-size:10px}.spinner{border:2px solid #becfbe;border-top-color:var(--green);border-radius:50%;flex-shrink:0;width:25px;height:25px;animation:.8s linear infinite spin;display:inline-block}.spinner.tiny{width:16px;height:16px}.primary .spinner{border-color:#fff #ffffff45 #ffffff45}@keyframes spin{to{transform:rotate(360deg)}}.page-loader{color:#7a897f;justify-content:center;align-items:center;gap:14px;min-height:90vh;display:flex}.page-loader.in-page{min-height:430px}.notice{border:1px solid;border-radius:8px;justify-content:space-between;align-items:center;gap:14px;margin-bottom:14px;padding:10px 15px;font-size:12px;display:flex}.notice.error{color:#945d41;background:#fff4ef;border-color:#eddbc9}.asset-selection-notice,.draft-recovery-notice,.asset-selection-actions{flex-wrap:wrap}.asset-selection-notice strong,.draft-recovery-notice strong{margin-bottom:3px;display:block}.asset-selection-actions{gap:8px;display:flex}.notice.success{color:#477047;background:#edf5e9;border-color:#dbe8d2}.notice.info{color:#536c7e;background:#f0f4f7;border-color:#dfe7ef}.topbar{background:#fff;border-bottom:1px solid #e6eae1;justify-content:space-between;align-items:center;min-height:64px;padding:12px 20px;display:flex}.brand{align-items:center;gap:10px;display:flex}.brand-icon{color:var(--green);justify-content:center;align-items:center;display:flex}.brand strong{letter-spacing:1px;font-size:20px;line-height:1.5;display:block}.brand small{letter-spacing:2px;color:#94a38f;font-size:8px;font-weight:500;display:block}.version-tag{color:#77906c;border:1px solid #dce3d7;border-radius:4px;align-self:flex-start;margin-top:6px;margin-left:3px;padding:1px 5px;font-size:9px}.header-actions{color:#627268;align-items:center;gap:15px;display:flex}.header-divider{background:#e4e9e0;width:1px;height:24px;margin:0 5px}.count{background:#eef2e9;border-radius:4px;padding:1px 5px;font-size:9px}.avatar{color:#638059;background:#e6eddf;border-radius:50%;justify-content:center;align-items:center;width:29px;height:29px;font-size:12px;display:flex}.user-name{margin-left:-8px;font-size:12px}.app-shell main{max-width:1700px;margin:auto;padding:20px 20px 12px}.workspace-title{justify-content:space-between;align-items:center;margin-bottom:24px;display:flex}.workspace-title h1{letter-spacing:.2px;margin:4px 0;font-size:27px;line-height:1.7}.workspace-title p{color:#8a968b;font-size:12px}.title-dot{color:#b8c59f}.workspace-title>.secondary{margin-top:9px}.environment-strip{color:#91957f;background:#f0f2e8;border:1px solid #e4e7d8;border-radius:7px;justify-content:space-between;align-items:center;gap:15px;margin-bottom:21px;padding:10px 14px;font-size:10px;display:flex}.environment-strip>div{align-items:center;gap:8px;display:flex}.environment-strip strong{color:#7f8268;font-weight:500}.status-dot{background:#6b956d;border-radius:50%;flex-shrink:0;width:6px;height:6px;display:inline-block}.status-dot.amber{background:#baab70}.workspace-grid{grid-template-columns:294px minmax(350px,1fr) 290px;align-items:start;gap:20px;display:grid}.panel{border:1px solid var(--line);border-radius:var(--radius);background:#fff;overflow:hidden;box-shadow:0 2px 5px #274c2402}.panel-heading{justify-content:space-between;align-items:center;gap:9px;padding:22px 23px 0;display:flex}.panel-heading h2{letter-spacing:.3px;text-overflow:ellipsis;white-space:nowrap;max-width:320px;margin-top:4px;font-size:17px;overflow:hidden}.source-panel .panel-heading{margin-bottom:3px}.source-section:last-of-type{border:0}.section-label{justify-content:space-between;align-items:center;margin-bottom:12px;display:flex}.section-label h3{font-size:13px}.section-label>span{color:#a0aa9c;font-size:10px}.two-actions{grid-template-columns:1fr 1fr;gap:9px;display:grid}.two-actions .secondary{padding:9px 5px;font-size:11px}.selected-patterns{grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-top:13px;display:grid}.pattern-tile .checker{background-color:#f9fbf5;border:1px solid #e8ece4;border-radius:7px;justify-content:center;align-items:center;height:64px;padding:10px;display:flex;position:relative}.checker{background-image:linear-gradient(45deg,#e9ede31a 25%,#0000 25%),linear-gradient(-45deg,#e9ede333 25%,#0000 25%),linear-gradient(45deg,#0000 75%,#e9ede333 75%),linear-gradient(-45deg,#0000 75%,#e9ede333 75%);background-position:0 0,0 6px,6px -6px,-6px 0;background-size:12px 12px}.pattern-tile img{object-fit:contain;width:46px;height:46px}.unavailable-pattern{color:#945d41;font-size:11px}.pattern-tile>span{text-align:center;white-space:nowrap;text-overflow:ellipsis;color:#677b68;margin-top:6px;font-size:10px;display:block;overflow:hidden}.remove-asset{color:#73906e;background:#fff;border:0;border-radius:50%;justify-content:center;align-items:center;width:17px;height:17px;padding:0;font-size:14px;line-height:1;display:flex;position:absolute;top:3px;right:3px}.remove-asset:hover{background:#e2ebda}.empty-patterns{color:#9aaa91;background:#fafcf7;border:1px dashed #d8e2d1;border-radius:8px;flex-direction:column;align-items:center;gap:6px;width:100%;margin-top:13px;padding:18px 8px;display:flex}.empty-patterns span{font-size:10px}.empty-patterns small{color:#b0baaa;font-size:9px}.template-grid{grid-template-columns:1fr 1fr;gap:9px;display:grid}.template-card{background:#fff;border:1px solid #e2e8df;border-radius:7px;min-width:0;padding:6px;position:relative;overflow:hidden}.template-card img{object-fit:cover;opacity:.85;border-radius:3px;width:100%;height:42px}.template-card>span{color:#82927d;justify-content:center;align-items:center;gap:6px;padding:6px 0 2px;font-size:11px;display:flex}.template-card.selected{background:#fbfcf8;border-color:#648666;box-shadow:inset 0 0 0 1px #648666}.template-card.selected>span{color:#3d6546;font-weight:600}.template-card:hover:not(:disabled){border-color:#719774}.background-selected{background:#f4f7ee;border:1px solid #e3e9db;border-radius:7px;align-items:center;gap:10px;margin-top:12px;padding:9px;display:flex}.background-selected img{object-fit:cover;border-radius:4px;width:39px;height:34px}.background-selected>div{flex:1;min-width:0}.background-selected strong{white-space:nowrap;text-overflow:ellipsis;font-size:11px;font-weight:500;display:block;overflow:hidden}.background-selected small{color:#95a28d;margin-top:2px;font-size:9px;display:block}.background-selected>svg{color:#799371}.empty-background{color:#a3ac9c;text-align:center;padding:17px 4px 0;font-size:10px}.background-section .microcopy{margin-top:9px}.selection-warning{color:#aa8650;background:#fff6e8;border-radius:7px;margin:0 15px 18px;padding:10px;font-size:11px;line-height:1.8}.center-column{flex-direction:column;gap:17px;min-width:0;display:flex}.preview-panel .panel-heading{padding:22px 24px 20px}.state-pill{color:#7c9672;white-space:nowrap;background:#f1f6ec;border-radius:5px;align-items:center;gap:5px;padding:5px 8px;font-size:9px;display:inline-flex}.state-pill.working{color:#a58c55;background:#f6f2e6}.state-pill.working .status-dot{background:#bfa363}.preview-stage{background-color:#f5f7ef;background-image:linear-gradient(#e7ebdf55 5%,#eff2e700 5%),linear-gradient(90deg,#eff2e700 95%,#e7ebdf55 95%);background-position:0 0;background-repeat:repeat;background-size:20px 20px;background-attachment:scroll;background-origin:padding-box;background-clip:border-box;border:1px solid #e6eadd;border-radius:10px;flex-direction:column;min-height:330px;margin:0 23px;display:flex;position:relative;overflow:hidden}.stage-topline,.stage-bottomline{color:#a4b095;justify-content:space-between;align-items:center;padding:14px 15px;font-size:9px;display:flex}.stage-topline>span:first-child{color:#899f79;font-size:10px}.stage-bottomline{letter-spacing:1px;margin-top:auto;font-size:8px}.stage-bottomline>span:first-child{letter-spacing:.2px}.preview-stage.is-filled{min-height:0}.ribbon-display{scrollbar-width:thin;scrollbar-color:#cfd8c2 transparent;flex:1;align-items:center;min-height:0;padding:18px 0;display:flex;overflow:auto hidden}.ribbon-display::-webkit-scrollbar{height:6px}.ribbon-display::-webkit-scrollbar-thumb{background:#cfd8c2;border-radius:3px}.ribbon-display img{border-radius:2px;flex:none;display:block;box-shadow:0 7px 12px #3351350a}.ribbon-display.detail img{width:auto;max-width:none;height:168px}.ribbon-display.fit img{width:100%;height:auto;max-height:none}.ribbon-tools{color:#94a385;align-items:center;gap:12px;padding:0 15px 14px;font-size:10px;display:flex}.ribbon-zoom{border:1px solid #dfe5d5;border-radius:6px;flex:none;display:inline-flex;overflow:hidden}.ribbon-zoom button{color:#7d8f6f;cursor:pointer;background:#fff;border:0;padding:4px 10px;font-size:10px}.ribbon-zoom button.is-active{color:#4e6343;background:#eef2e6;font-weight:500}.ribbon-metrics{font-variant-numeric:tabular-nums;letter-spacing:.2px;white-space:nowrap;text-overflow:ellipsis;overflow:hidden}.ribbon-hint{white-space:nowrap;color:#b0bc9f;margin-left:auto}.preview-stage.is-empty{min-height:330px}.empty-canvas{text-align:center;flex-direction:column;flex:1;justify-content:center;align-items:center;padding:10px 15px 15px;display:flex}.empty-symbol{color:#98ad7f;background:#e9efdf;border-radius:18px;justify-content:center;align-items:center;width:56px;height:56px;margin-bottom:12px;display:flex}.empty-canvas h3{color:#839575;font-size:14px;font-weight:500}.empty-canvas p{color:#a6b09a;margin-top:7px;font-size:10px;line-height:1.9}.template-peek{color:#a1af90;border-top:1px solid #e2e9d9;align-items:center;gap:8px;margin-top:15px;padding-top:12px;font-size:9px;display:flex}.template-peek img{object-fit:cover;opacity:.65;border-radius:3px;width:85px;height:24px}.processing-overlay{-webkit-backdrop-filter:blur(3px);backdrop-filter:blur(3px);background:#f8faf1d9;flex-direction:column;justify-content:center;align-items:center;gap:10px;display:flex;position:absolute;inset:0}.processing-overlay strong{font-size:13px;font-weight:500}.processing-overlay>span:last-child{color:#91a086;font-size:10px}.preview-caption{color:#a4af9a;justify-content:space-between;align-items:center;padding:11px 24px 0;font-size:9px;display:flex}.preview-caption>span:first-child{align-items:center;gap:5px;display:flex}.result-actions{grid-template-columns:1fr 1fr;gap:12px;padding:19px 23px 0;display:grid}.result-actions .primary,.result-actions .secondary{padding:12px 8px;font-size:12px}.generate-area>.primary{font-size:13px}.generate-area>.primary svg:last-child{margin-left:auto}.generate-area>.primary svg:first-child{margin-right:auto}.generate-area>small{text-align:center;color:#9eaa94;padding-top:10px;font-size:10px;display:block}.history-hint{color:#9caa90;padding:12px 24px 0;font-size:10px}.history-hint button{color:#507644;background:0 0;border:0;padding:0 0 0 5px;font-size:10px;text-decoration:underline}.history-panel{padding:20px 22px 21px}.history-heading{justify-content:space-between;align-items:center;gap:7px;margin-bottom:16px;display:flex}.history-heading h3{font-size:13px}.history-heading>span{color:#a9b19f;font-size:9px}.version-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;display:grid}.version-card{text-align:left;background:#fff;border:1px solid #e5eadf;border-radius:8px;min-width:0;padding:8px}.version-card.selected{background:#fcfdf9;border-color:#7a9969;box-shadow:inset 0 0 0 1px #7a9969}.version-card>img{object-fit:cover;background:#f4f6ed;border-radius:3px;width:100%;height:46px}.version-card>div{justify-content:space-between;align-items:center;gap:5px;margin-top:8px;display:flex}.version-card strong{font-size:11px;font-weight:500}.version-card>div>small{color:#a9b19d;font-size:9px}.version-card .tiny-pill{padding:1px 5px;font-size:8px}.version-parent{white-space:nowrap;text-overflow:ellipsis;color:#a8b29c;margin-top:5px;font-size:8px;display:block;overflow:hidden}.empty-history{color:#aab69f;justify-content:center;align-items:center;gap:12px;min-height:63px;font-size:10px;display:flex}.history-line{background:#e2e9d9;width:25px;height:1px}.handoff-note{color:#9baa92;align-items:center;gap:11px;padding:1px 9px;display:flex}.note-icon{color:#94a681;background:#eaf0e2;border-radius:50%;flex-shrink:0;justify-content:center;align-items:center;width:34px;height:34px;display:flex}.handoff-note strong{color:#91a180;font-size:10px;font-weight:500;display:block}.handoff-note span:not(.note-icon){margin-top:2px;font-size:9px;display:block}.text-limit{text-align:right;color:#aeb9a1;margin-top:4px;font-size:8px}.page-footer{color:#b2bba7;justify-content:space-between;align-items:center;margin-top:29px;font-size:9px;display:flex}.page-footer>span:first-child{letter-spacing:1px}.page-footer>span:nth-child(2){letter-spacing:2px}.modal-scrim{-webkit-backdrop-filter:blur(4px);backdrop-filter:blur(4px);z-index:20;background:#16392a55;justify-content:center;align-items:center;padding:24px;display:flex;position:fixed;inset:0}.modal{background:#fff;border-radius:18px;width:520px;max-width:100%;max-height:90vh;padding:27px 30px;overflow:auto;box-shadow:0 20px 80px #142f2733}.modal-wide{width:840px}.modal-heading{justify-content:space-between;align-items:center;margin-bottom:25px;display:flex}.modal-heading h2{margin-top:5px;font-size:23px}.modal-heading .eyebrow{font-size:8px}.modal-footer{border-top:1px solid var(--line);justify-content:space-between;align-items:center;gap:15px;margin-top:22px;padding-top:20px;display:flex}.modal-footer>span{color:#8fa180;font-size:11px}.modal-footer>.primary{padding:10px 17px;font-size:12px}.library-toolbar{gap:12px;display:flex}.library-toolbar>input{flex:1;font-size:12px}.upload-label{cursor:pointer;font-size:12px}.upload-label.disabled{opacity:.5;pointer-events:none}.checkbox-line{color:#859775;align-items:center;gap:8px;margin:12px 0;font-size:11px;display:flex!important}.library-note{margin:15px 0;font-size:11px}.library-grid{grid-template-columns:repeat(4,minmax(0,1fr));gap:15px;display:grid}.library-card{text-align:left;background:#fff;border:1px solid #e2e9da;border-radius:9px;width:100%;padding:7px;overflow:hidden}.library-card.selected{background:#fafcf6;border-color:#7b9a67;box-shadow:inset 0 0 0 1px #7b9a67}.library-image{background-color:#f7f9f1;border-radius:5px;justify-content:center;align-items:center;height:100px;display:flex;position:relative}.library-image img{object-fit:contain;width:100%;max-height:100%;padding:8px}.library-image:not(.checker) img{object-fit:cover;height:100%;padding:0}.check-mark{color:#fff;background:#3b6c41;border-radius:50%;justify-content:center;align-items:center;width:20px;height:20px;display:flex;position:absolute;top:6px;right:6px}.library-card strong{text-overflow:ellipsis;white-space:nowrap;margin:9px 4px 4px;font-size:12px;font-weight:500;display:block;overflow:hidden}.library-card>span{color:#a0ad92;margin:0 4px 5px;font-size:9px;display:block}.hide-asset{color:#a5af9c;background:0 0;border:0;padding:5px 3px;font-size:9px}.hide-asset:hover{color:#a2765c}.empty-library{text-align:center;color:#9fae91;padding:45px 10px;font-size:12px}.design-library{flex-direction:column;gap:10px;display:flex}.design-list-item{text-align:left;background:#fff;border:1px solid #e4eadc;border-radius:9px;align-items:center;gap:15px;padding:15px;display:flex}.design-list-item.selected{background:#f6f9ef;border-color:#afc299}.design-list-item>div{flex:1}.design-list-item strong{font-size:13px;font-weight:500;display:block}.design-list-item small{color:#a0ae90;margin-top:4px;font-size:10px;display:block}.design-list-icon{color:#95ae79;background:#edf3e4;border-radius:10px;justify-content:center;align-items:center;width:42px;height:42px;display:flex}.design-list-item>svg{color:#a5b890}.admin-tabs{border-bottom:1px solid #e5eadf;gap:8px;margin-bottom:18px;padding-bottom:15px;display:flex}.admin-tabs button{color:#899a7b;background:0 0;border:0;border-radius:7px;padding:9px 15px;font-size:12px}.admin-tabs button.active{color:#50713a;background:#eaf2df}.admin-intro{color:#91a17f;justify-content:space-between;align-items:center;margin-bottom:16px;font-size:12px;display:flex}.table-scroll{max-height:450px;overflow:auto}.table-scroll table{border-collapse:collapse;width:100%;font-size:11px}.table-scroll th{text-align:left;color:#95a582;white-space:nowrap;background:#f5f8ed;font-size:10px;font-weight:500}.table-scroll th,.table-scroll td{border-bottom:1px solid #e9efdf;padding:12px 10px}.table-scroll td{word-break:break-word;color:#7e936a;max-width:240px}.table-scroll td strong{font-size:10px;font-weight:500;display:block}.table-scroll td small{color:#a2b48c;margin-top:4px;font-size:9px;display:block}.job-status{background:#f3f4ec;border-radius:4px;padding:3px 5px;font-size:9px}.job-status.succeeded{background:#ebf3e0}.job-status.failed{color:#a88463;background:#fff1e6}.admin-columns{grid-template-columns:1fr 1fr;gap:28px;display:grid}.admin-columns h3{margin-bottom:14px}.admin-form label{color:#849970;margin-bottom:15px;font-size:11px;display:block}.admin-form label input,.admin-form label select,.admin-form label textarea{margin-top:6px;font-size:12px}.admin-form>small{color:#a0b18a;margin-top:-8px;margin-bottom:15px;font-size:9px;display:block}.admin-form>.primary{width:100%;margin-top:12px;font-size:12px}.admin-form>.text-button{justify-content:center;width:100%;margin-top:7px;font-size:10px}.admin-form .checkbox-line input{margin:0}.code-input{font-family:Consolas,monospace}.admin-existing{max-height:530px;overflow:auto}.admin-template{text-align:left;background:#fff;border:1px solid #e4ecd9;border-radius:7px;align-items:center;gap:10px;width:100%;margin-bottom:9px;padding:9px;display:flex}.admin-template.selected{background:#f5f9ec;border-color:#acc58d}.admin-template img{object-fit:cover;border-radius:4px;width:87px;height:35px}.admin-template>div{flex:1}.admin-template strong{font-size:11px;font-weight:500;display:block}.admin-template small{color:#a4b58e;margin-top:3px;font-size:9px;display:block}.admin-template>svg{color:#a5b58e}.profile-item{border:1px solid #e6eddb;border-radius:8px;margin-top:10px;padding:13px 10px}.profile-item strong{justify-content:space-between;align-items:center;gap:7px;font-size:12px;font-weight:500;display:flex}.profile-item small,.profile-item>span{color:#a1b28a;margin-top:5px;font-size:10px;display:block}.form-two{grid-template-columns:1fr 1fr;gap:12px;display:grid}.admin-intro+.table-scroll+.microcopy{margin-top:15px}.login-page{grid-template-columns:1.1fr 1fr;min-height:100vh;display:grid}.login-illustration{background:#edf2e5;flex-direction:column;justify-content:space-between;padding:50px 9%;display:flex;position:relative;overflow:hidden}.login-illustration>div:nth-child(2){margin:60px 0 30px}.login-illustration h1{letter-spacing:1px;color:#385b36;margin:17px 0 20px;font-size:49px;font-weight:550;line-height:1.5}.login-illustration p{color:#92a77f;font-size:13px;line-height:2.1}.login-illustration .eyebrow{color:#8da478;letter-spacing:1px;font-size:11px}.decorative-ribbon{background:#dce9ca;border-top:1px solid #cfdfbd;border-bottom:1px solid #cfdfbd;justify-content:space-around;align-items:center;gap:20px;width:140%;margin-left:-20%;padding:28px 23px;display:flex;transform:rotate(-8deg);box-shadow:0 15px 30px #6e855518}.decorative-ribbon span{color:#9caf76;font-size:45px}.decorative-ribbon span:nth-child(3n+1){color:#d3aa7d;font-size:54px}.decorative-ribbon span:nth-child(3n+2){color:#cebf7c}.login-illustration>small{letter-spacing:3px;color:#a3b58f;margin-top:60px;font-size:9px}.login-form-wrap{background:#fff;justify-content:center;align-items:center;padding:40px;display:flex}.login-form{width:350px;max-width:100%}.login-form>h2{margin:9px 0 12px;font-size:27px}.login-form>.muted{margin-bottom:30px;font-size:12px}.login-form>label{color:#6e8563;margin-bottom:19px;font-size:12px;display:block}.login-form>label>input{margin-top:8px;padding:12px 14px}.login-form>.primary{justify-content:space-between;margin-top:10px}.login-demo{color:#a0af91;border-top:1px solid #e9efdf;margin-top:30px;padding-top:20px;font-size:11px}.login-demo strong{margin-bottom:8px;font-size:10px;font-weight:500;display:block}.login-demo span{margin:3px 0;font-size:10px;display:block}.login-demo small{color:#b0bda3;margin-top:12px;font-size:9px;display:block}@media (width>=1500px){.workspace-grid{grid-template-columns:315px minmax(480px,1fr) 310px;gap:24px}.source-section{padding:23px}.preview-stage{min-height:380px}.template-card img{height:48px}.empty-canvas{min-height:280px}.panel-heading{padding-top:25px}.preview-stage.is-empty{min-height:380px}}@media (width<=1200px){.workspace-grid{grid-template-columns:260px minmax(300px,1fr) 255px;gap:14px}.app-shell main{padding:25px 2.5% 20px}.topbar{padding:0 2.5%}.source-section{padding:20px 17px}.panel-heading{padding-left:18px;padding-right:18px}.preview-panel .panel-heading{padding:22px 17px 19px}.preview-stage{margin:0 17px}.result-actions{padding-left:17px;padding-right:17px}.panel-heading h2{max-width:190px;font-size:15px}.preview-stage{min-height:310px}.state-pill{font-size:8px}.stage-topline,.stage-bottomline{padding:11px}.preview-caption{padding-left:17px;padding-right:17px}.history-panel{padding:18px 16px}.history-heading>span{font-size:8px}.template-card>span{font-size:10px}.selected-patterns{gap:7px}.pattern-tile .checker{height:59px;padding:7px}.template-card img{height:38px}.source-section .section-label>span{font-size:9px}.brand strong{font-size:18px}}@media (width<=1000px){.workspace-grid{grid-template-columns:250px minmax(360px,1fr);gap:18px}.source-panel{grid-row:span 2}.center-column{grid-column:2}.environment-strip>div>span:last-child{display:none}.workspace-title h1{font-size:23px}.page-footer>span:nth-child(2){display:none}.login-illustration h1{font-size:38px}}@media (width<=700px){.topbar{height:70px;padding:0 18px}.brand strong{font-size:16px}.brand small{letter-spacing:1.5px;font-size:6px}.brand-icon svg{width:20px}.version-tag{display:none}.header-actions{gap:5px}.header-actions>.text-button{gap:0;padding:8px;font-size:0}.header-actions>.text-button .count,.header-divider,.user-name{display:none}.avatar{width:25px;height:25px;margin-left:5px}.app-shell main{padding:22px 16px 18px}.workspace-title{align-items:start;gap:10px}.workspace-title h1{margin:7px 0;font-size:21px;line-height:1.6}.workspace-title p{max-width:240px;font-size:10px;line-height:1.8}.workspace-title .eyebrow{font-size:8px}.workspace-title>.secondary{gap:0;margin-top:20px;padding:10px;font-size:0}.workspace-grid{grid-template-columns:1fr;gap:17px}.source-panel,.center-column{grid-area:auto/1}.source-panel{overflow:visible}.source-section{padding:18px}.source-panel .panel-heading{padding:20px 18px 0}.source-section:first-of-type .two-actions{max-width:300px}.selected-patterns{flex-wrap:wrap;gap:10px;display:flex}.pattern-tile{width:65px}.empty-patterns{padding:12px}.template-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.template-card img{height:34px}.template-card>span{font-size:10px}.template-card{padding:5px}.environment-strip{gap:7px;padding:9px 10px;font-size:9px}.environment-strip strong{font-size:9px}.outline-pill{padding:3px 5px;font-size:8px}.environment-strip>div{gap:6px}.background-section .two-actions,.background-selected{max-width:300px}.preview-stage{min-height:285px}.preview-stage.is-empty{min-height:300px}.preview-panel .panel-heading h2{max-width:225px}.history-panel{padding:20px 18px}.page-footer{gap:12px;font-size:8px}.modal-scrim{padding:10px}.modal{border-radius:12px;max-height:94vh;padding:22px 18px}.modal-heading{margin-bottom:20px}.modal-heading h2{font-size:21px}.library-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.library-image{height:80px}.library-card strong{font-size:10px}.library-card>span{font-size:8px}.library-toolbar{gap:7px}.upload-label{padding:10px;font-size:10px}.library-toolbar input{min-width:0;font-size:11px}.modal-footer{gap:10px}.modal-footer>span{font-size:10px}.modal-footer>.primary{padding:10px 12px;font-size:11px}.admin-columns{grid-template-columns:1fr}.admin-existing{max-height:240px}.login-page{flex-direction:column;min-height:100vh;display:flex}.login-illustration{min-height:320px;padding:25px 30px 30px}.login-illustration>div:nth-child(2){margin:30px 0 0}.login-illustration h1{margin:10px 0 14px;font-size:30px;line-height:1.4}.login-illustration h1 br{display:none}.login-illustration p{font-size:11px}.decorative-ribbon,.login-illustration>small{display:none}.login-form-wrap{flex:1;padding:35px 30px 40px}.login-form>h2{font-size:24px}.login-form>.eyebrow{font-size:8px}.login-demo{margin-top:23px}.notice{font-size:11px}}@media (prefers-reduced-motion:reduce){*{transition:none!important;animation-duration:.01ms!important}}@container (width<=950px){.workspace-grid{grid-template-columns:250px minmax(0,1fr);gap:16px}.source-panel{grid-row:span 2}.center-column{grid-column:2}.topbar{flex-wrap:wrap;gap:12px}.workspace-title h1{font-size:22px}}@container (width<=700px){.workspace-grid{grid-template-columns:minmax(0,1fr)}.source-panel,.center-column{grid-area:auto/1}.topbar,.app-shell main{padding:14px}.workspace-title,.environment-strip{flex-wrap:wrap}.header-actions>.text-button{gap:5px;font-size:12px}.workspace-title>.secondary{margin-top:0;font-size:12px}}.template-option{flex-direction:column;gap:3px;min-width:0;display:flex}.template-option>.template-card{width:100%}.more-layouts{border-top:1px solid var(--line);margin-top:12px}.more-layouts-toggle{color:#345e45;background:0 0;border:0;justify-content:space-between;align-items:center;width:100%;min-height:40px;padding:9px 2px;font-size:13px;font-weight:600;display:flex}.more-layouts-toggle:hover{background:#edf3e9}.chosen-layout{justify-content:space-between;align-items:center;gap:8px;margin-top:8px;font-size:12px;display:flex}.chosen-layout .template-example-button{font-size:11px}.layout-picker-modal,.asset-library-modal,.design-library-modal{flex-direction:column;max-height:calc(100dvh - 48px);display:flex;overflow:hidden}.layout-picker-modal>.modal-heading,.asset-library-modal>.modal-heading,.design-library-modal>.modal-heading,.asset-library-modal>.library-toolbar,.asset-library-modal>.library-note,.asset-library-modal>.checkbox-line,.layout-picker-modal>.library-note,.layout-picker-modal>.modal-footer,.asset-library-modal>.modal-footer,.design-library-modal>.modal-footer{flex-shrink:0}.layout-picker-grid.template-grid{grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;min-height:0;padding:3px;overflow:auto}.asset-library-modal>.library-grid,.design-library-modal>.design-library{min-height:0;padding:3px;overflow:auto}.library-pagination{color:#526a5d;flex-shrink:0;justify-content:space-between;align-items:center;gap:12px;padding-top:16px;font-size:12px;display:flex}.design-loading{gap:12px}.preview-panel>.result-actions,.preview-panel>.generate-area{padding-top:0;padding-bottom:16px}.ai-draft-options{color:#3d5a43;background:#f7faf3;border:1px solid #e1e9da;border-radius:7px;margin-top:12px;padding:10px 12px;font-size:12px}.ai-draft-options>label{align-items:center;gap:8px;font-weight:600;display:flex}.ai-draft-options input{accent-color:#3b6c41;width:auto;margin:0}.ai-draft-options p{color:#65765f;margin:7px 0 0;font-size:11px;line-height:1.7}.ai-draft-reference{flex-wrap:wrap;align-items:center;gap:8px;margin-top:7px;font-size:11px;display:flex}.ai-draft-reference button,.ai-reference-picker{color:#345e45;text-underline-offset:3px;background:0 0;border:0;padding:4px 0;font-size:11px;text-decoration:underline}.ai-reference-picker{margin-top:5px}.layout-reference-help{color:#526a5d;margin-top:12px;font-size:13px;line-height:1.8}.choose-ai-reference{margin-top:14px;font-size:13px}.design-list-row{align-items:center;gap:10px;display:flex}.design-list-row>.design-list-item{flex:1;min-width:0}.design-list-item>div{min-width:0}.design-list-item strong{overflow-wrap:anywhere}.design-list-tabs{flex-shrink:0;gap:10px;padding-bottom:16px;display:flex}.design-list-tabs>button{border:1px solid var(--line);color:#526a5d;background:#fff;border-radius:6px;padding:8px 16px}.design-list-tabs>button.selected{color:#345e45;background:#edf3e9;border-color:#afc299}.delete-design-button{color:#965246;background:0 0;border:1px solid #eadbd7;border-radius:6px;flex-shrink:0;padding:9px 12px}.delete-design-confirm{color:#724638;background:#fff8f3;border:1px solid #e9d7cb;border-radius:8px;flex-shrink:0;margin-bottom:15px;padding:14px;font-size:13px}.delete-design-confirm>div{justify-content:flex-end;gap:10px;margin-top:12px;display:flex}.danger-button{color:#fff;background:#9e4634;border:1px solid #9e4634;border-radius:6px;padding:8px 14px;font-size:12px}@media (width<=700px){.layout-picker-grid.template-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.library-pagination{gap:6px;font-size:11px}.library-pagination .secondary{padding:8px}}.layout-selection-help,.layout-selection-issue{margin-top:12px;font-size:12px;line-height:1.7}.layout-selection-help{color:#526a5d}.layout-selection-issue{color:#9e4634}.template-rules-help{color:#526a5d;font-size:12px;line-height:1.7;display:block}.template-example-button,.template-examples-all{color:#345e45;text-underline-offset:3px;background:0 0;border:0;font-size:12px;font-weight:500;line-height:1.5;text-decoration:underline}.template-example-button{min-height:30px;padding:4px 6px}.template-examples-all{padding:4px 0 4px 8px}.template-example-button:hover,.template-examples-all:hover{color:#193f29;background:#edf3e9}.template-example-button:focus-visible,.template-examples-all:focus-visible{outline-offset:2px;outline:2px solid #507857}.layout-examples-modal{width:1160px}.pattern-role{color:#284a36;background:#fff;border:1px solid #b8c7b1;border-radius:5px;width:100%;min-width:0;min-height:30px;margin-top:5px;padding:3px 5px;font-size:12px}.pattern-role-help{color:var(--muted);margin:10px 0 0;font-size:12px;line-height:1.5}.selected-patterns.has-pattern-roles{grid-template-columns:repeat(2,minmax(80px,1fr))}.has-pattern-roles .pattern-tile{min-width:80px}.layout-examples-modal .modal-heading{z-index:2;background:#fff;margin-top:-12px;margin-bottom:14px;padding-top:12px;padding-bottom:12px;position:sticky;top:-27px}.layout-examples-intro{margin-bottom:22px}.layout-mode-summary{color:#284a36;margin:0 0 8px;font-size:16px;line-height:1.65}.layout-mode-note{color:#455b49;background:#f2f6ee;border-left:3px solid #90a77f;margin:8px 0 12px;padding:10px 13px;font-size:14px;line-height:1.7}.layout-examples-tools{flex-wrap:wrap;align-items:center;gap:14px;display:flex}.layout-examples-tools>button{min-height:34px;font-size:13px}.case-mode-filter{align-items:center;gap:8px;font-size:14px;display:flex}.case-mode-filter select{min-height:36px}.layout-case-navigation{align-items:center;gap:12px;margin:14px 0;display:flex}.layout-case-navigation>label{flex:1;align-items:center;gap:12px;min-width:0;display:flex}.layout-case-navigation>label>span{white-space:nowrap;color:#42583d;font-size:13px}.layout-case-navigation select{flex:1;min-width:0;min-height:36px}.layout-example-kind{flex-wrap:wrap;gap:8px;margin:12px 0 18px;display:flex}.layout-example-kind button{color:#37513d;background:#fff;border:1px solid #bdcdb6;border-radius:6px;padding:8px 14px;font-size:14px}.layout-example-kind button.selected{background:#e9f0e4;border-color:#67855b;font-weight:600}.layout-example-difference{color:#695626;margin:8px 0 0;font-size:14px;line-height:1.7}.layout-demo-note{color:#42583d;font-size:14px;line-height:1.7}.layout-demos figure{border-top:1px solid #dbe5d7;margin:16px 0;padding-top:14px}.layout-demos figcaption{flex-direction:column;gap:6px;margin-bottom:8px;font-size:14px;line-height:1.6;display:flex}.layout-demos figcaption span{color:#42583d}.layout-demos figure>img{object-fit:contain;background:#f6f8f2;border:1px solid #dbe5d7;border-radius:5px;width:100%;height:auto;max-height:250px;display:block}@media (width<=600px){.layout-case-navigation{gap:6px}.layout-case-navigation>label{flex-direction:column;align-items:stretch;gap:4px}}.layout-examples-loading,.layout-examples-error{color:#37513d;flex-wrap:wrap;align-items:center;gap:14px;min-height:140px;display:flex}.layout-examples-error{padding:20px 0;display:block}.layout-examples-error>p{margin:0 0 16px;font-size:15px;line-height:1.7}.layout-examples-list{flex-direction:column;gap:22px;display:flex}.layout-example{border-top:1px solid #dbe5d7;min-width:0;padding-top:18px}.layout-example-heading{flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:12px;display:flex}.layout-example-heading h3{color:#284a36;margin:0;font-size:19px;line-height:1.5}.layout-example-heading>div{flex-wrap:wrap;align-items:center;gap:12px;display:flex}.layout-example-code{color:#50624d;font-variant-numeric:tabular-nums;font-size:13px}.layout-reference-tag{color:#6b5828;background:#f4f1e6;border-radius:4px;padding:3px 7px;font-size:12px}.layout-example-description{color:#304f3a;margin:8px 0 0;font-size:15px;line-height:1.7}.layout-example-image-tools{align-items:center;gap:12px;min-height:38px;display:flex}.layout-example-image-tools>button{color:#335c40;min-height:34px;padding:5px 0;font-size:13px}.layout-example-image-tools>span{color:#53644d;font-size:12px}.layout-example-viewport{background:#f7f9f5;border:1px solid #e3e9df;border-radius:5px;overflow:auto hidden}.layout-example-viewport>img{width:100%;max-width:none;height:auto;display:block}.layout-example-viewport.is-zoomed>img{width:max(100%, var(--example-width))}.layout-example-viewport:focus-visible{outline-offset:3px;outline:2px solid #507857}.layout-example-look{color:#3e5941;margin:10px 0 0;font-size:14px;line-height:1.7}.layout-example-look strong{font-weight:600}.layout-example-reference{color:#6b5828;margin:8px 0 0;font-size:13px;line-height:1.7}.layout-example-unavailable{color:#465d48;background:#f7f9f5;border:1px dashed #b8c7b1;border-radius:5px;margin-top:14px;padding:18px;font-size:14px;line-height:1.7}.layout-example-unavailable p{margin:0}.layout-example-unavailable button{margin-top:12px;font-size:13px}.layout-examples-source{color:#53644d;border-top:1px solid #dbe5d7;margin:20px 0 0;padding-top:14px;font-size:12px;line-height:1.8}.background-prompt-label{color:var(--ink);margin:12px 0 6px;font-size:13px;font-weight:600;display:block}.background-prompt{box-sizing:border-box;border:1px solid var(--line);width:100%;min-height:66px;color:var(--ink);font:inherit;resize:vertical;background:#fff;border-radius:6px;padding:9px 10px;font-size:13px;line-height:1.65;display:block}.background-prompt:focus{outline-offset:2px;outline:2px solid #91a88a}.model-help{color:#4c634f;font-size:13px;line-height:1.7}@media (width<=600px){.layout-examples-modal .modal-heading{top:-20px}.layout-examples-modal .modal-heading h2{font-size:20px}.layout-mode-summary{font-size:15px}.layout-example-heading h3{font-size:17px}.layout-example-heading{gap:4px}}.background-tone-control{color:#42584b;align-items:center;gap:8px;margin-top:12px;font-size:13px;display:flex}.background-tone-control input[type=checkbox]{accent-color:#386b43;width:16px;height:16px;margin:0}.density-control{align-items:center;gap:12px;margin-top:12px;font-size:13px;display:flex}.density-control select{color:#203c2a;background:#fff;border:1px solid #d7dfd6;border-radius:6px;flex:1;min-width:0;padding:6px 10px}.loop-preview{min-width:0;padding:0 15px 12px}.loop-view-heading{color:#35523d;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:8px;margin:0 0 10px;display:flex}.loop-view-heading strong{font-size:13px;font-weight:600}.loop-view-heading>span{font-variant-numeric:tabular-nums;font-size:10px}.loop-unit-view{justify-content:center;align-items:center;min-height:150px;padding:14px 0;display:flex}.loop-unit-view .loop-image>img{width:auto;max-width:100%;height:auto;max-height:220px;display:block;box-shadow:0 5px 14px #33513514}.loop-continuity{min-width:0;padding:14px 0}.loop-unit-view[hidden],.loop-continuity[hidden]{display:none}.loop-continuity-track{grid-template-columns:repeat(3,minmax(0,1fr));align-items:stretch;display:grid}.loop-repeat{min-width:0;position:relative}.loop-repeat>img{border:0;border-radius:0;width:100%;max-width:none;height:auto;display:block}.loop-continuity-track.show-seams>.loop-repeat+.loop-repeat:before{content:\"\";z-index:1;pointer-events:none;border-left:2px dashed #aa3d4c;width:0;position:absolute;top:-9px;bottom:-9px;left:-1px}.loop-preview-tools{flex-wrap:wrap;align-items:center;gap:14px;padding-top:8px;display:flex}.loop-view-button{color:#305e3d;background:#fff;border:1px solid #bacbb1;border-radius:6px;min-height:32px;padding:6px 10px;font-size:12px}.loop-view-button[aria-pressed=true]{background:#e8f0e2}.loop-seam-toggle{color:#486044;align-items:center;gap:6px;font-size:12px;display:inline-flex}.loop-seam-toggle input{accent-color:#386b43;width:15px;height:15px;margin:0}.loop-preview-note{color:#53664d;margin:9px 0 0;font-size:11px;line-height:1.7}.loop-check{color:#3e5d38;background:#edf4e8;border:1px solid #d5e1ce;border-radius:6px;margin-top:10px;padding:9px 11px;font-size:11px;line-height:1.7}.loop-check>strong{margin-right:9px;font-weight:600;display:inline}.loop-check.needs-review{color:#73552a;background:#fff8e9;border-color:#e7d7b4}.loop-check ul{margin:6px 0 0;padding-left:17px}.loop-check li.error{color:#933f35}.loop-mode-notice{color:#725832;margin-top:8px;font-size:11px;line-height:1.7}.loop-technical-details{color:#53664d;margin-top:9px;font-size:11px;line-height:1.7}.loop-technical-details summary{cursor:pointer;width:fit-content}.loop-technical-details dl{margin:7px 0 0}.loop-technical-details dl>div{gap:12px;display:flex}.loop-technical-details dt{flex:none}.loop-technical-details dd{overflow-wrap:anywhere;margin:0}@media (width<=600px){.loop-preview{padding-left:10px;padding-right:10px}.loop-unit-view{min-height:110px}.loop-unit-view .loop-image>img{max-height:170px}.loop-view-heading{display:block}.loop-view-heading>span{margin-top:3px;display:block}}.loop-image{max-width:100%;position:relative}.optional-layers{padding:12px 0}.optional-layers summary{cursor:pointer;font-weight:600}.optional-layers>div{flex-wrap:wrap;align-items:center;gap:8px;margin-top:8px;display:flex}.compact-status.environment-strip{color:#485c4d;flex-wrap:wrap;justify-content:flex-start;min-height:0;margin:8px 0;padding:7px 12px}.compact-status.environment-strip span{font-size:12px;display:inline}.workspace-grid{margin-top:12px}.panel-heading h2{margin:0}.history-panel summary{cursor:pointer;color:#344b3e;font-size:14px;font-weight:600}.image-recovery{color:#73552a;background:#fff8e9;flex-direction:column;justify-content:center;align-items:center;gap:8px;min-height:90px;padding:10px;font-size:13px;line-height:1.6;display:flex}.image-recovery [role=button]{cursor:pointer;align-items:center;min-height:32px;display:flex}.image-loading{color:#42584b;padding:3px;font-size:12px;line-height:1.6;display:block}.loop-image .image-loading,.loop-repeat .image-loading{position:absolute;bottom:0;left:0;right:0}.preview-stage{min-height:230px}@media (width>=1100px){.preview-column{align-self:start;position:sticky;top:12px}}.workspace-grid{grid-template-columns:220px minmax(0,1fr) 250px;gap:16px}@media (width>=1500px){.workspace-grid{grid-template-columns:230px minmax(0,1fr) 260px;gap:20px}}@container (width>=701px) and (width<=1050px){.workspace-grid{grid-template-rows:max-content max-content minmax(0,1fr);grid-template-columns:220px minmax(0,1fr)}.source-panel{grid-row:1/span 3}.center-column{grid-area:1/2}}@container (width>=1051px){.center-column{align-self:start;position:sticky;top:12px}}@container (width<=700px){.workspace-grid{grid-template-columns:minmax(0,1fr)}.source-panel,.center-column{grid-area:auto/1}}.library-note,.hide-asset,.library-card>span,.modal-footer>span{color:#42584b}.loop-resolution-note{color:#7a5a12;background:#fffaf0;border:1px solid #f0dfb4;border-radius:8px;margin:6px 0 0;padding:8px 12px;font-size:12.5px;line-height:1.6}.style-control{gap:6px;margin-top:10px;display:grid}.style-control>span{color:#5b6a83;font-size:12.5px}.style-chips{flex-wrap:wrap;gap:8px;display:flex}.style-chip{color:#33435c;cursor:pointer;background:#fff;border:1px solid #dfe6ef;border-radius:999px;padding:6px 12px;font-size:12.5px}.style-chip.selected{color:#1f3f96;background:#eef3ff;border-color:#315ccc;font-weight:600}.style-chip:disabled{opacity:.55;cursor:not-allowed}.style-hint{color:#7a8aa3;margin:0;font-size:12px}.candidate-gallery{grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-top:12px;display:grid}.candidate-card{background:#fff;border:1px solid #e2e8f1;border-radius:10px;margin:0;overflow:hidden}.candidate-card img{background:#f4f6fa;width:100%;height:auto;display:block}.candidate-card figcaption{gap:6px;padding:8px 10px 10px;display:grid}.candidate-card figcaption strong{font-size:13px}:host{--ink:#151b26;--ink-soft:#3b4657;--muted:#78849a;--faint:#9aa5b6;--line:#e6e9f0;--line-strong:#d6dbe6;--surface:#fff;--canvas:#f6f7fa;--accent:#1d2939;--accent-hover:#273246;--accent-soft:#eef1f7;--radius:14px;color:var(--ink);background:var(--canvas);letter-spacing:.01em;font-family:Inter,HarmonyOS Sans SC,Noto Sans SC,Microsoft YaHei,system-ui,sans-serif;font-size:13.5px}.topbar{border-bottom:1px solid var(--line);-webkit-backdrop-filter:saturate(160%)blur(12px);backdrop-filter:saturate(160%)blur(12px);z-index:20;background:#ffffffdb;min-height:60px;padding:0 28px;position:sticky;top:0}.topbar .brand strong,.brand strong{letter-spacing:-.01em;color:var(--ink);font-size:15px;font-weight:650}.topbar .header-actions{gap:6px}.topbar .header-actions .secondary,.topbar .header-actions .text-button{color:var(--ink-soft);border-radius:999px;font-size:12.5px;font-weight:500}.topbar .header-actions .secondary{border:1px solid var(--line-strong);background:#fff}.topbar .header-actions .secondary:hover:enabled{background:#fbfcfe;border-color:#b9c2d2}main{padding:22px 28px 40px}.panel{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 1px 2px #151b260a,0 12px 28px -22px #151b2647}.panel-heading{border-bottom:1px solid var(--line);align-items:flex-start;padding:18px 22px 14px}.panel-heading h2{letter-spacing:-.01em;color:var(--ink);font-size:15px;font-weight:650}.panel-sub{color:var(--faint);margin:3px 0 0;font-size:12px;font-weight:400}.panel-heading>svg{color:var(--faint)}.source-section{border-bottom:1px solid var(--line);padding:18px 22px}.source-section:last-of-type{border-bottom:0}.section-label{align-items:center;margin-bottom:12px}.section-label h3{letter-spacing:.02em;color:var(--ink);align-items:center;gap:8px;font-size:12.5px;font-weight:600;display:inline-flex}.step-index{background:var(--accent-soft);width:18px;height:18px;color:var(--ink-soft);letter-spacing:0;border-radius:999px;justify-content:center;align-items:center;font-size:10.5px;font-weight:600;display:inline-flex}.section-meta{color:var(--faint);font-size:11.5px;font-weight:400}.quiet-link{color:var(--muted);cursor:pointer;background:0 0;border:0;padding:0;font-size:11.5px;font-weight:500}.quiet-link:hover{color:var(--ink);text-underline-offset:3px;text-decoration:underline}button.primary,a.primary{background:var(--accent);color:#fff;letter-spacing:.01em;border-radius:999px;font-weight:550;box-shadow:0 8px 18px -14px #151b26b3}button.primary:hover:enabled,a.primary:hover{background:#273246}button.secondary{border:1px solid var(--line-strong);color:var(--ink-soft);background:#fff;border-radius:999px;font-weight:500}button.secondary:hover:enabled{background:#fbfcfe;border-color:#b9c2d2}button.secondary.small,button.primary.small{border-radius:999px;min-height:28px;padding:5px 12px;font-size:11.5px}.text-button{color:var(--muted);background:0 0;border:0}.text-button:hover:enabled{color:var(--ink)}.inline-field{color:var(--muted);gap:5px;margin-top:12px;font-size:11.5px;display:grid}.inline-field select,.density-control select,.background-tone-control select{border:1px solid var(--line-strong);width:100%;color:var(--ink);background:#fff;border-radius:9px;padding:7px 10px;font-size:12.5px}.field-label{color:var(--muted);font-size:11.5px}.selected-patterns{gap:10px}.pattern-tile{border-radius:10px}.pattern-tile>span{color:var(--muted);font-size:11px}.empty-patterns{border:1px dashed var(--line-strong);color:var(--muted);background:#fbfcfe;border-radius:12px}.empty-patterns:hover:enabled{background:#f8fafd;border-color:#b9c2d2}.template-card{border:1px solid var(--line);background:#fff;border-radius:11px;padding:5px}.template-card.selected{border-color:var(--ink);box-shadow:0 0 0 1px var(--ink)}.template-card span{color:var(--ink-soft);font-size:11px}.layout-help{border-top:1px solid var(--line);margin-top:10px;padding-top:8px}.layout-help summary{color:var(--muted);cursor:pointer;font-size:11.5px}.layout-help p{color:var(--muted);margin:6px 0 0;font-size:11.5px;line-height:1.65}.layout-selection-issue{color:#a4483f;margin:8px 0 0;font-size:11.5px}.style-control{gap:7px;margin-top:14px}.style-chips{gap:6px}.style-chip{border:1px solid var(--line-strong);color:var(--ink-soft);background:#fff;border-radius:999px;padding:5px 12px;font-size:11.5px;font-weight:500}.style-chip:hover:enabled{border-color:#b9c2d2}.style-chip.selected{border-color:var(--ink);background:var(--ink);color:#fff;font-weight:550}.style-hint{color:var(--faint);font-size:11px;line-height:1.6}.trial-box{border:1px solid var(--line);background:#fbfcfe;border-radius:12px;margin-top:14px;padding:10px 12px}.trial-box>summary{cursor:pointer;color:var(--ink-soft);align-items:baseline;gap:8px;font-size:12px;font-weight:600;list-style:none;display:flex}.trial-box>summary::-webkit-details-marker{display:none}.trial-box>summary small{color:var(--faint);font-size:10.5px;font-weight:400}.trial-body{gap:10px;margin-top:10px;display:grid}.trial-chips{flex-wrap:wrap;gap:6px;display:flex}.trial-chip{border:1px solid var(--line-strong);color:var(--ink-soft);background:#fff;border-radius:999px;align-items:center;gap:6px;padding:4px 11px 4px 7px;font-size:11.5px;display:inline-flex}.trial-chip .trial-check{border:1px solid var(--line-strong);color:#fff;border-radius:999px;justify-content:center;align-items:center;width:14px;height:14px;font-size:9px;display:inline-flex}.trial-chip.selected{border-color:var(--ink);background:var(--accent-soft);color:var(--ink)}.trial-chip.selected .trial-check{background:var(--ink);border-color:var(--ink)}.candidate-gallery{gap:10px;margin-top:12px}.candidate-card{border:1px solid var(--line);background:#fff;border-radius:12px}.candidate-card.selected{border-color:var(--ink);box-shadow:0 0 0 1px var(--ink)}.candidate-card figcaption{gap:5px;padding:8px 10px 10px}.candidate-card figcaption strong{color:var(--ink);font-size:12px;font-weight:600}.candidate-card figcaption span{color:var(--faint);font-size:10.5px}.close-trial{place-self:end start}.background-prompt-box{margin-top:10px}.background-prompt-box>summary{color:var(--muted);cursor:pointer;align-items:baseline;gap:6px;font-size:11.5px;display:flex}.background-prompt-box>summary small{color:var(--faint);font-size:10.5px}.background-prompt{border:1px solid var(--line-strong);border-radius:10px;min-height:56px;margin-top:8px;padding:9px 11px;font-size:12px}.background-selected{border:1px solid var(--line);background:#fbfcfe;border-radius:11px;margin-top:10px;padding:8px}.background-selected strong{font-size:12px;font-weight:600}.background-selected small{color:var(--faint);font-size:10.5px}.empty-background{border:1px dashed var(--line-strong);color:var(--faint);text-align:center;border-radius:11px;margin-top:10px;padding:14px;font-size:11.5px}.preview-panel{padding-bottom:18px}.preview-stage{border:1px solid var(--line);background-color:#fbfcfe;background-image:linear-gradient(#eef1f7 4%,#fff0 4%),linear-gradient(90deg,#fff0 96%,#eef1f7 96%);background-size:26px 26px;border-radius:12px;margin:16px 22px 0}.stage-topline{letter-spacing:.06em;text-transform:uppercase;color:var(--faint);padding:10px 14px 0;font-size:10.5px}.state-pill{color:var(--muted);background:#f2f4f8;border-radius:999px;padding:4px 10px;font-size:10.5px}.state-pill.working{background:var(--accent-soft);color:var(--ink-soft)}.result-actions,.generate-area{margin-top:14px;padding:0 22px}.generate-area>small{color:var(--faint);text-align:center;margin-top:6px;font-size:11px;display:block}.ribbon-tools{color:var(--muted);padding:10px 14px 12px;font-size:11px}.ribbon-zoom button{border:1px solid var(--line-strong);color:var(--ink-soft);background:#fff;border-radius:999px;padding:4px 12px;font-size:11px}.ribbon-zoom button.is-active{background:var(--ink);border-color:var(--ink);color:#fff}.text-limit{color:var(--faint);font-size:10.5px}.environment-strip{border:1px solid var(--line);color:var(--muted);background:#fbfcfe;border-radius:10px;margin-bottom:14px;padding:8px 14px;font-size:11.5px}.notice{border-radius:10px;font-size:12px}.page-footer{color:var(--faint);border-top:1px solid var(--line);margin-top:26px;padding-top:14px;font-size:11px}.workspace-grid{grid-template-columns:258px minmax(0,1fr) 268px;align-items:start;gap:18px}@container (width>=1051px){.center-column{top:76px}}@container (width>=701px) and (width<=1050px){.workspace-grid{grid-template-columns:220px minmax(0,1fr);gap:16px}.center-column{position:static}}@container (width<=700px){.workspace-grid{grid-template-columns:minmax(0,1fr)}.center-column{position:static}}.history-panel{margin-top:14px}.image-quiet{color:#b3bccb;background:#f3f5f9;border-radius:8px;justify-content:center;align-items:center;min-height:44px;display:flex}.template-card .image-quiet{aspect-ratio:16/10;width:100%}.template-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.template-card{padding:5px}.template-card img,.template-card .image-quiet{object-fit:cover;border-radius:7px;width:100%;height:54px;min-height:0}.template-card span{text-overflow:ellipsis;white-space:nowrap;padding:4px 2px 1px;font-size:10.5px;display:block;overflow:hidden}.template-example-button{color:var(--muted);text-align:left;background:0 0;border:0;padding:3px 2px;font-size:10.5px}.template-example-button:hover{color:var(--ink);text-underline-offset:3px;text-decoration:underline}.template-option{align-content:start;display:grid}.sr-only{clip:rect(0 0 0 0);white-space:nowrap;border:0;width:1px;height:1px;margin:-1px;padding:0;position:absolute;overflow:hidden}.result-actions{justify-content:flex-end;align-items:center;gap:10px;display:flex}.result-actions .primary{max-width:320px;padding-inline:26px}.stage-topline span:last-child{color:var(--muted);letter-spacing:0;text-transform:none;font-size:11px}.preview-caption{color:var(--faint);font-size:11px}.generate-area>.primary.full{border-radius:12px;min-height:42px}.trial-box>summary{flex-direction:column;align-items:flex-start;gap:2px}.trial-box>summary small{display:block}.trial-progress{background:#e8ebf2;border-radius:999px;height:4px;overflow:hidden}.trial-progress>span{background:var(--ink);border-radius:999px;height:100%;transition:width .25s;display:block}.candidate-card.is-pending{border-style:dashed}.candidate-skeleton{min-height:96px;color:var(--faint);background:#f6f7fa;justify-content:center;align-items:center;display:flex}.workspace-grid{grid-template-rows:auto;grid-template-columns:280px minmax(0,1fr);align-items:start;gap:20px}.source-panel{grid-area:1/1}.center-column{grid-area:1/2;min-width:0;position:sticky;top:76px}.preview-panel{position:static}.generate-area{padding:12px 20px 16px}.generate-area>.primary.full{min-height:42px}.generate-area>small{color:var(--muted);margin-top:7px;display:block}.result-actions{padding-bottom:0}@container (width>=701px) and (width<=1050px){.workspace-grid{grid-template-columns:235px minmax(0,1fr);gap:16px}.center-column{position:static}}@container (width<=700px){.workspace-grid{grid-template-columns:minmax(0,1fr);gap:16px}.source-panel,.center-column{grid-area:auto/1;position:static}}.workspace-actions{flex-wrap:wrap;justify-content:space-between;align-items:center;gap:10px;display:flex}.workspace-actions .generation-button{flex:1;justify-content:center;max-width:360px;min-height:42px}.workspace-actions .result-actions{flex-wrap:wrap;padding:0}.ai-draft-options{background:0 0;border:0;border-radius:0;flex-wrap:wrap;align-items:center;gap:8px 14px;margin:10px 0 0;padding:0;display:flex}.ai-draft-options p{margin:0;font-size:12px}.ai-draft-reference{margin:0}.generate-area>small:empty{display:none}@container (width<=700px){.workspace-actions{align-items:stretch}.workspace-actions .generation-button{max-width:none}.workspace-actions .result-actions{justify-content:flex-start}}";
// src/embed.tsx
function j(e, t) {
	let n = e.shadowRoot || e.attachShadow({ mode: "open" }), r = document.createElement("style");
	r.textContent = Ee;
	let i = document.createElement("div");
	n.replaceChildren(r, i), y(t);
	let a = (0, u.createRoot)(i), o = !0, s = "ribbon", c = () => a.render(/* @__PURE__ */ (0, w.jsx)(we, {
		active: o,
		view: s
	}));
	return c(), {
		setView(e, t = !0) {
			o = t, s = e, c();
		},
		unmount() {
			a.unmount(), n.replaceChildren();
		}
	};
}
export { j as mount };
