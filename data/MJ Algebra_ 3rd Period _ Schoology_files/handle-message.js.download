"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.handlePutMessageRequest = exports.calculateSizeOfObject = exports.preparePostMessageErrorResponse = exports.preparePostMessageSuccessResponse = exports.attemptToStoreData = exports.handleMessage = exports.main = exports.ErrorMessage = exports.ErrorCode = void 0;
const RESPONSE_SUFFIX = '.response';
var SUBJECT_TYPES;
(function (SUBJECT_TYPES) {
    SUBJECT_TYPES["PUT"] = "lti.put_data";
    SUBJECT_TYPES["GET"] = "lti.get_data";
    SUBJECT_TYPES["CAPABILITIES"] = "lti.capabilities";
})(SUBJECT_TYPES || (SUBJECT_TYPES = {}));
const SUBJECT_PUT_RESPONSE = SUBJECT_TYPES.PUT + RESPONSE_SUFFIX;
const SUBJECT_GET_RESPONSE = SUBJECT_TYPES.GET + RESPONSE_SUFFIX;
const SUBJECT_CAPABILITIES_RESPONSE = SUBJECT_TYPES.CAPABILITIES + RESPONSE_SUFFIX;
var ErrorCode;
(function (ErrorCode) {
    ErrorCode["STORAGE_EXHAUSTED"] = "storage_exhausted";
    ErrorCode["BAD_REQUEST"] = "bad_request";
    ErrorCode["KEY_NOT_FOUND"] = "key_not_found";
})(ErrorCode = exports.ErrorCode || (exports.ErrorCode = {}));
var ErrorMessage;
(function (ErrorMessage) {
    ErrorMessage["PUT_KEY_NOT_PROVIDED"] = "The put_data request is missing the 'key' field.";
    ErrorMessage["SUBJECT_NOT_RECOGNIZED"] = "Unrecognized postMessage subject";
    ErrorMessage["EVENT_DATA_INVALID"] = "Data is in invalid format";
    ErrorMessage["ORIGIN_MISMATCH"] = "The expected origin did not match for the tool";
    ErrorMessage["KEY_DOES_NOT_EXIST"] = "Key does not exist";
    ErrorMessage["NO_VALUE"] = "There is no value stored for this key";
})(ErrorMessage = exports.ErrorMessage || (exports.ErrorMessage = {}));
function main(toolOrigin, maxMessageSize, maxMessageKeysCount, messageFrameName) {
    const localStorage = {};
    window.addEventListener('message', event => {
        handleMessage(event, toolOrigin, localStorage, maxMessageSize, maxMessageKeysCount, messageFrameName);
    });
}
exports.main = main;
function handleMessage(event, toolOrigin, localStorage, maxMessageSize, maxMessageKeysCount, messageFrameName) {
    const { data, origin } = event;
    if (origin !== toolOrigin || typeof event.data !== 'object') {
        const errorMessage = origin !== toolOrigin ? ErrorMessage.ORIGIN_MISMATCH : ErrorMessage.EVENT_DATA_INVALID;
        event.source.postMessage(preparePostMessageErrorResponse(ErrorCode.BAD_REQUEST, errorMessage), origin);
        return;
    }
    const { subject, message_id: messageId, key, value = null } = data;
    let responseMessage;
    switch (subject) {
        case SUBJECT_TYPES.GET:
            if (!localStorage[origin] || !localStorage[origin][key]) {
                responseMessage = preparePostMessageErrorResponse(ErrorCode.KEY_NOT_FOUND, ErrorMessage.NO_VALUE, SUBJECT_GET_RESPONSE, messageId);
            }
            else {
                responseMessage = preparePostMessageSuccessResponse(key, localStorage[origin][key], SUBJECT_GET_RESPONSE, messageId);
            }
            break;
        case SUBJECT_TYPES.PUT:
            if (!localStorage[origin]) {
                localStorage[origin] = {};
            }
            responseMessage = handlePutMessageRequest(key, value, messageId, localStorage[origin], maxMessageSize, maxMessageKeysCount);
            break;
        case SUBJECT_TYPES.CAPABILITIES:
            const CAPABILITIES = [
                {
                    subject: SUBJECT_TYPES.CAPABILITIES,
                    frame: messageFrameName,
                },
                {
                    subject: SUBJECT_TYPES.PUT,
                    frame: messageFrameName,
                },
                {
                    subject: SUBJECT_TYPES.GET,
                    frame: messageFrameName,
                },
            ];
            responseMessage = {
                message_id: messageId,
                subject: SUBJECT_CAPABILITIES_RESPONSE,
                supported_messages: CAPABILITIES,
            };
            break;
        default:
            responseMessage = preparePostMessageErrorResponse(ErrorCode.BAD_REQUEST, ErrorMessage.SUBJECT_NOT_RECOGNIZED, subject, messageId);
    }
    event.source.postMessage(responseMessage, origin);
}
exports.handleMessage = handleMessage;
function attemptToStoreData(key, value, maxMessageKeysCount, maxMessageSize, localStorageOrigin) {
    const ERROR_STORAGE_LIMIT_EXHAUSTED = 'Storage limit for the messages has been exceeded which is ' + maxMessageSize + ' bytes';
    const ERROR_KEY_COUNT_EXCEEDED = 'Number of allowed keys exceeded which is ' + maxMessageKeysCount;
    if (Object.keys(localStorageOrigin).length === maxMessageKeysCount) {
        return {
            success: false,
            errorMessage: ERROR_KEY_COUNT_EXCEEDED,
        };
    }
    localStorageOrigin[key] = value;
    const sizeOfLocalStorageForOrigin = calculateSizeOfObject(localStorageOrigin);
    if (sizeOfLocalStorageForOrigin > maxMessageSize) {
        delete localStorageOrigin[key];
        return {
            success: false,
            errorMessage: ERROR_STORAGE_LIMIT_EXHAUSTED,
        };
    }
    return {
        success: true,
        errorMessage: '',
    };
}
exports.attemptToStoreData = attemptToStoreData;
function preparePostMessageSuccessResponse(key, value, subject, messageId) {
    return {
        subject,
        key,
        value,
        message_id: messageId,
    };
}
exports.preparePostMessageSuccessResponse = preparePostMessageSuccessResponse;
function preparePostMessageErrorResponse(code, message, subject = null, messageId = null) {
    if (!(subject && messageId)) {
        return {
            error: {
                code,
                message,
            },
        };
    }
    return {
        subject,
        message_id: messageId,
        error: {
            code,
            message,
        },
    };
}
exports.preparePostMessageErrorResponse = preparePostMessageErrorResponse;
function calculateSizeOfObject(obj) {
    let totalSize = 0;
    const bytesPerChar = 2;
    for (const key in obj) {
        if (obj.hasOwnProperty(key)) {
            {
                const value = obj[key];
                totalSize += key.length * bytesPerChar;
                if (typeof value === 'string') {
                    totalSize += value.length * bytesPerChar;
                }
                else {
                    const jsonString = JSON.stringify(value);
                    totalSize += jsonString.length * bytesPerChar;
                }
            }
        }
    }
    return totalSize;
}
exports.calculateSizeOfObject = calculateSizeOfObject;
function handlePutMessageRequest(key, value, messageId, originLocalStorage, maxMessageSize, maxMessageKeysCount) {
    if (!key) {
        return preparePostMessageErrorResponse(ErrorCode.BAD_REQUEST, ErrorMessage.PUT_KEY_NOT_PROVIDED, SUBJECT_PUT_RESPONSE, messageId);
    }
    if (!value) {
        if (originLocalStorage[key]) {
            delete originLocalStorage[key];
            return preparePostMessageSuccessResponse(key, undefined, SUBJECT_PUT_RESPONSE, messageId);
        }
        return preparePostMessageErrorResponse(ErrorCode.BAD_REQUEST, ErrorMessage.KEY_DOES_NOT_EXIST, SUBJECT_PUT_RESPONSE, messageId);
    }
    const response = attemptToStoreData(key, value, maxMessageKeysCount, maxMessageSize, originLocalStorage);
    if (!response.success) {
        return preparePostMessageErrorResponse(ErrorCode.STORAGE_EXHAUSTED, response.errorMessage, SUBJECT_PUT_RESPONSE, messageId);
    }
    return preparePostMessageSuccessResponse(key, value, SUBJECT_PUT_RESPONSE, messageId);
}
exports.handlePutMessageRequest = handlePutMessageRequest;
//# sourceMappingURL=handle-message.js.map