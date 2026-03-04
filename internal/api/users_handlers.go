package api

import (
	"database/sql"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"github.com/cbaguilar/svwatergo/internal/users"
	"github.com/gin-gonic/gin"
)

type UsersAPI struct {
	Store *users.Store
}

func NewUsersAPI(store *users.Store) *UsersAPI {
	return &UsersAPI{Store: store}
}

func (a *UsersAPI) ListUsers(c *gin.Context) {
	if a == nil || a.Store == nil {
		c.JSON(http.StatusServiceUnavailable, errJSON("Unavailable", "user management is not configured", nil))
		return
	}
	list, err := a.Store.ListUsers(c.Request.Context())
	if err != nil {
		c.JSON(http.StatusInternalServerError, errJSON("UsersListFailed", "failed to list users", nil))
		return
	}
	c.JSON(http.StatusOK, gin.H{"users": list})
}

func (a *UsersAPI) CreateUser(c *gin.Context) {
	if a == nil || a.Store == nil {
		c.JSON(http.StatusServiceUnavailable, errJSON("Unavailable", "user management is not configured", nil))
		return
	}
	var req struct {
		Email string `json:"email"`
		Role  int    `json:"role"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, errJSON("InvalidRequest", "invalid JSON body", nil))
		return
	}
	user, err := a.Store.CreateUser(c.Request.Context(), req.Email, req.Role)
	if err != nil {
		status := http.StatusBadRequest
		if isUniqueViolation(err) {
			status = http.StatusConflict
		}
		c.JSON(status, errJSON("CreateUserFailed", err.Error(), nil))
		return
	}
	c.JSON(http.StatusCreated, gin.H{"user": user})
}

func (a *UsersAPI) UpdateUser(c *gin.Context) {
	if a == nil || a.Store == nil {
		c.JSON(http.StatusServiceUnavailable, errJSON("Unavailable", "user management is not configured", nil))
		return
	}
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil || id <= 0 {
		c.JSON(http.StatusBadRequest, errJSON("InvalidUserID", "invalid user id", nil))
		return
	}
	var req struct {
		Email string `json:"email"`
		Role  int    `json:"role"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, errJSON("InvalidRequest", "invalid JSON body", nil))
		return
	}
	user, err := a.Store.UpdateUser(c.Request.Context(), id, req.Email, req.Role)
	if err != nil {
		switch {
		case errors.Is(err, sql.ErrNoRows):
			c.JSON(http.StatusNotFound, errJSON("UserNotFound", "user not found", nil))
		case isUniqueViolation(err):
			c.JSON(http.StatusConflict, errJSON("UpdateUserFailed", "email already exists", nil))
		default:
			c.JSON(http.StatusBadRequest, errJSON("UpdateUserFailed", err.Error(), nil))
		}
		return
	}
	c.JSON(http.StatusOK, gin.H{"user": user})
}

func (a *UsersAPI) DeleteUser(c *gin.Context) {
	if a == nil || a.Store == nil {
		c.JSON(http.StatusServiceUnavailable, errJSON("Unavailable", "user management is not configured", nil))
		return
	}
	id, err := strconv.ParseInt(c.Param("id"), 10, 64)
	if err != nil || id <= 0 {
		c.JSON(http.StatusBadRequest, errJSON("InvalidUserID", "invalid user id", nil))
		return
	}
	if err := a.Store.DeleteUser(c.Request.Context(), id); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			c.JSON(http.StatusNotFound, errJSON("UserNotFound", "user not found", nil))
			return
		}
		c.JSON(http.StatusBadRequest, errJSON("DeleteUserFailed", err.Error(), nil))
		return
	}
	c.JSON(http.StatusOK, gin.H{"deleted": id})
}

func isUniqueViolation(err error) bool {
	if err == nil {
		return false
	}
	s := strings.ToLower(err.Error())
	return strings.Contains(s, "unique constraint") || strings.Contains(s, "duplicate key value")
}
